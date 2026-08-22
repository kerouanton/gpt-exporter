import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Index a local ChatGPT archive into a searchable SQLite FTS5 database.

Version 4 schema adds:
- native conversation provenance detection (standard / Custom GPT / Project),
- multiple manual categories per conversation,
- multiple manual tags per conversation,
- multiple manual work projects per conversation (independent of native ChatGPT Projects),
- human labels for opaque origin IDs,
- category/tag/origin filtering,
- bulk category/tag assignment from an FTS query,
- uncategorized/untagged listing helpers,
- an explicit rebuild command for disposable index databases.

Version 2.6 CLI safety adds:
- relevance previews for bulk tag/category assignment,
- dry-run-by-default bulk classification,
- explicit --apply before bulk writes,
- --title-only / --min-occurrences / --min-messages thresholds,
- tag-suggest / category-suggest commands,
- tag-clear / category-clear with preview-by-default semantics.

Version 2.7 project organization adds:
- first-class work projects spanning conversations from any origin,
- succinct project listing and per-project conversation views,
- project filters and unprojected conversation listing.

Designed for Python 3.12+ on Windows. It uses only the standard library.
"""

import argparse
import datetime as dt
import json
import logging
import lzma
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Sequence


DEFAULT_ARCHIVE_ROOT = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents" / "ChatGPT Archive"
DEFAULT_DOWNLOADS_DIR = DEFAULT_ARCHIVE_ROOT / "downloads"
DEFAULT_DATABASE_PATH = DEFAULT_ARCHIVE_ROOT / "conversations-index.sqlite"
SCHEMA_VERSION = 4

LOGGER = logging.getLogger("chatgpt_archive_indexer")

EXCLUDED_CONTENT_TYPES = {
    "user_editable_context",
    "model_editable_context",
    "thoughts",
    "reasoning_recap",
}
INDEXABLE_ROLES = {"user", "assistant"}
WHITESPACE_RE = re.compile(r"\s+")
FILENAME_SAFE_RE = re.compile(r"[^\w.-]+", re.UNICODE)
ORIGIN_TYPES = {"custom_gpt", "project", "other"}


# ---------------------------------------------------------------------------
# Logging and text helpers
# ---------------------------------------------------------------------------


def configure_logging(debug: bool) -> None:
    """Configure verbose, timestamped console logging."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def normalize_text(value: Any) -> str:
    """Return human-readable text from a ChatGPT content value."""
    if value is None:
        return ""
    if isinstance(value, str):
        return WHITESPACE_RE.sub(" ", value).strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (normalize_text(item) for item in value))).strip()
    if isinstance(value, dict):
        if "text" in value:
            return normalize_text(value["text"])
        if "parts" in value:
            return normalize_text(value["parts"])
    return ""


def optional_string(value: Any) -> str | None:
    """Return a useful string scalar, or None for empty/non-scalar values."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def iso_datetime(unix_timestamp: Any) -> str | None:
    """Convert an export timestamp to a local ISO 8601 timestamp."""
    if not isinstance(unix_timestamp, (int, float)):
        return None
    return dt.datetime.fromtimestamp(
        unix_timestamp, tz=dt.timezone.utc
    ).astimezone().isoformat()


def now_iso() -> str:
    """Return the current local timestamp in ISO 8601 format."""
    return dt.datetime.now().astimezone().isoformat()


# ---------------------------------------------------------------------------
# Conversation/message extraction
# ---------------------------------------------------------------------------


def extract_message_text(message: dict[str, Any]) -> str:
    """Extract searchable text while avoiding raw metadata and tool internals."""
    content = message.get("content") or {}
    content_type = content.get("content_type")

    if content_type in {"text", "code", "multimodal_text"}:
        return normalize_text(content.get("parts"))

    return normalize_text(content.get("text") or content.get("parts"))


def is_visible_indexable_message(message: dict[str, Any]) -> bool:
    """Keep only normal user and assistant turns intended to be visible."""
    role = message.get("author", {}).get("role")
    if role not in INDEXABLE_ROLES:
        return False

    metadata = message.get("metadata") or {}
    if metadata.get("is_visually_hidden_from_conversation"):
        return False

    content = message.get("content") or {}
    if content.get("content_type") in EXCLUDED_CONTENT_TYPES:
        return False

    return bool(extract_message_text(message))


def conversation_messages(conversation: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield visible messages in export mapping order."""
    mapping = conversation.get("mapping") or {}
    for node in mapping.values():
        message = node.get("message") if isinstance(node, dict) else None
        if isinstance(message, dict) and is_visible_indexable_message(message):
            yield message


def slugify(value: str) -> str:
    """Create a broadly compatible filename fragment."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = FILENAME_SAFE_RE.sub("_", value).strip("_. ")
    return value or "Untitled"


def find_docx(archive_root: Path, conversation_id: str) -> Path | None:
    """Find the DOCX whose filename contains this stable conversation identifier."""
    candidates = list(archive_root.glob(f"*_{conversation_id}.docx"))
    if not candidates:
        candidates = list(archive_root.rglob(f"*{conversation_id}*.docx"))
    if len(candidates) > 1:
        LOGGER.warning(
            "Multiple DOCX files match %s; using %s",
            conversation_id,
            candidates[0],
        )
    return candidates[0] if candidates else None


def read_conversation(json_path: Path) -> dict[str, Any]:
    """Read one compressed conversation export."""
    with lzma.open(json_path, "rt", encoding="utf-8") as input_file:
        data = json.load(input_file)
    if not isinstance(data, dict) or not data.get("conversation_id"):
        raise ValueError("Missing object root or conversation_id")
    return data


# ---------------------------------------------------------------------------
# Native origin detection
# ---------------------------------------------------------------------------


def classify_origin_id(origin_id: str) -> str:
    """Classify a native ChatGPT origin identifier by its observed prefix."""
    if origin_id.startswith("g-p-"):
        return "project"
    if origin_id.startswith("g-"):
        return "custom_gpt"
    return "other"


def iter_nested_gizmo_ids(value: Any, path: str = "metadata") -> Iterable[tuple[str, str]]:
    """Yield nested gizmo_id values found in metadata-like structures."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "gizmo_id":
                candidate = optional_string(child)
                if candidate:
                    yield candidate, child_path
            if isinstance(child, (dict, list)):
                yield from iter_nested_gizmo_ids(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                yield from iter_nested_gizmo_ids(child, f"{path}[{index}]")


def detect_origins(conversation: dict[str, Any]) -> list[dict[str, str]]:
    """Detect Custom GPT / Project IDs without inferring from conversation text.

    Multiple origins are retained because a conversation may contain both a
    top-level native origin and message-level project/custom-GPT metadata.
    """
    discovered: dict[str, dict[str, str]] = {}

    def add(origin_id: str | None, source: str) -> None:
        if not origin_id:
            return
        current = discovered.get(origin_id)
        if current is None:
            discovered[origin_id] = {
                "origin_id": origin_id,
                "origin_type": classify_origin_id(origin_id),
                "source": source,
            }
        elif source not in current["source"].split(";"):
            current["source"] += ";" + source

    add(optional_string(conversation.get("gizmo_id")), "top_level.gizmo_id")
    add(
        optional_string(conversation.get("conversation_template_id")),
        "top_level.conversation_template_id",
    )

    mapping = conversation.get("mapping") or {}
    if isinstance(mapping, dict):
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not isinstance(message, dict):
                continue

            metadata = message.get("metadata")
            if isinstance(metadata, (dict, list)):
                for origin_id, path in iter_nested_gizmo_ids(metadata, "message.metadata"):
                    add(origin_id, path)

            content = message.get("content")
            if isinstance(content, dict):
                # Multimodal parts can carry their own metadata objects.
                for origin_id, path in iter_nested_gizmo_ids(content, "message.content"):
                    add(origin_id, path)

    # Stable ordering: projects first, then Custom GPTs, then anything unknown.
    type_priority = {"project": 0, "custom_gpt": 1, "other": 2}
    return sorted(
        discovered.values(),
        key=lambda item: (type_priority[item["origin_type"]], item["origin_id"]),
    )


def primary_origin(origins: Sequence[dict[str, str]]) -> tuple[str, str | None]:
    """Return a convenient primary origin while retaining all detected origins."""
    if not origins:
        return "standard", None
    first = origins[0]
    return first["origin_type"], first["origin_id"]


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------


def schema_exists(connection: sqlite3.Connection) -> bool:
    """Return True if an existing conversations table is present."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    return row is not None


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the complete v2 schema."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            source_json_path TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            docx_path TEXT,
            indexed_at TEXT NOT NULL,

            primary_origin_type TEXT NOT NULL DEFAULT 'standard',
            primary_origin_id TEXT,
            gizmo_id TEXT,
            gizmo_type TEXT,
            conversation_template_id TEXT,
            conversation_origin TEXT,
            default_model_slug TEXT
        );

        CREATE INDEX IF NOT EXISTS conversations_title_idx
            ON conversations(title COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS conversations_created_at_idx
            ON conversations(created_at);
        CREATE INDEX IF NOT EXISTS conversations_primary_origin_idx
            ON conversations(primary_origin_type, primary_origin_id);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            message_id TEXT NOT NULL,
            message_order INTEGER NOT NULL,
            author_role TEXT NOT NULL,
            created_at TEXT,
            content_type TEXT,
            body TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
            ON messages(conversation_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            body,
            title,
            conversation_id UNINDEXED,
            message_id UNINDEXED,
            author_role UNINDEXED
        );

        CREATE TABLE IF NOT EXISTS origins (
            origin_id TEXT PRIMARY KEY,
            origin_type TEXT NOT NULL,
            label TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS origins_type_idx
            ON origins(origin_type);

        CREATE TABLE IF NOT EXISTS conversation_origins (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            origin_id TEXT NOT NULL REFERENCES origins(origin_id)
                ON DELETE CASCADE,
            source TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0, 1)),
            PRIMARY KEY (conversation_id, origin_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_origins_origin_idx
            ON conversation_origins(origin_id);

        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_categories (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES categories(category_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, category_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_categories_category_idx
            ON conversation_categories(category_id);

        CREATE TABLE IF NOT EXISTS tags (
            tag_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_tags (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(tag_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, tag_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_tags_tag_idx
            ON conversation_tags(tag_id);

        CREATE TABLE IF NOT EXISTS work_projects (
            project_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_work_projects (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES work_projects(project_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, project_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_work_projects_project_idx
            ON conversation_work_projects(project_id);
        """
    )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def connect_database(database_path: Path, *, require_current: bool = True) -> sqlite3.Connection:
    """Open the archive database and validate/create/migrate the current schema."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    existing_schema = schema_exists(connection)
    user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    if not existing_schema:
        create_schema(connection)
    elif user_version in {2, 3}:
        LOGGER.info(
            "Migrating SQLite schema from version %d to version %d",
            user_version,
            SCHEMA_VERSION,
        )
        create_schema(connection)
    elif user_version == SCHEMA_VERSION:
        create_schema(connection)
    elif require_current:
        connection.close()
        raise ValueError(
            f"Database schema version is {user_version}, but this script requires "
            f"version {SCHEMA_VERSION}. Run the 'rebuild' command once."
        )

    return connection


def remove_database_files(database_path: Path) -> None:
    """Delete SQLite database, WAL and SHM files if present."""
    for path in (
        database_path,
        Path(str(database_path) + "-wal"),
        Path(str(database_path) + "-shm"),
    ):
        if path.exists():
            LOGGER.info("Deleting %s", path)
            path.unlink()


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


def delete_message_index_rows(
    connection: sqlite3.Connection, conversation_id: str
) -> None:
    """Delete message and FTS rows for one conversation, preserving categories."""
    old_ids = connection.execute(
        "SELECT id FROM messages WHERE conversation_id = ?", (conversation_id,)
    ).fetchall()
    for old_row in old_ids:
        connection.execute(
            "DELETE FROM messages_fts WHERE rowid = ?", (old_row["id"],)
        )
    connection.execute(
        "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
    )


def replace_detected_origins(
    connection: sqlite3.Connection,
    conversation_id: str,
    origins: Sequence[dict[str, str]],
    primary_origin_id: str | None,
) -> None:
    """Replace native origin links while preserving origin human labels."""
    connection.execute(
        "DELETE FROM conversation_origins WHERE conversation_id = ?",
        (conversation_id,),
    )
    timestamp = now_iso()

    for origin in origins:
        connection.execute(
            """
            INSERT INTO origins (
                origin_id, origin_type, label, first_seen_at, last_seen_at
            ) VALUES (?, ?, NULL, ?, ?)
            ON CONFLICT(origin_id) DO UPDATE SET
                origin_type = excluded.origin_type,
                last_seen_at = excluded.last_seen_at
            """,
            (
                origin["origin_id"],
                origin["origin_type"],
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO conversation_origins (
                conversation_id, origin_id, source, is_primary
            ) VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                origin["origin_id"],
                origin["source"],
                int(origin["origin_id"] == primary_origin_id),
            ),
        )


def index_one(
    connection: sqlite3.Connection,
    json_path: Path,
    archive_root: Path,
    *,
    force: bool = False,
) -> bool:
    """Update one conversation if its source export has changed."""
    source_mtime_ns = json_path.stat().st_mtime_ns
    conversation = read_conversation(json_path)
    conversation_id = conversation["conversation_id"]

    existing = connection.execute(
        "SELECT source_mtime_ns FROM conversations WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    if (
        not force
        and existing
        and existing["source_mtime_ns"] == source_mtime_ns
    ):
        LOGGER.debug("Unchanged: %s", json_path.name)
        return False

    title = normalize_text(conversation.get("title")) or "Untitled conversation"
    docx = find_docx(archive_root, conversation_id)
    indexed_at = now_iso()
    visible_messages = list(conversation_messages(conversation))
    origins = detect_origins(conversation)
    primary_type, primary_id = primary_origin(origins)

    LOGGER.debug(
        "Origin detection for %s: primary=%s/%s all=%s",
        conversation_id,
        primary_type,
        primary_id,
        [(item["origin_type"], item["origin_id"]) for item in origins],
    )

    with connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id,
                title,
                created_at,
                updated_at,
                source_json_path,
                source_mtime_ns,
                docx_path,
                indexed_at,
                primary_origin_type,
                primary_origin_id,
                gizmo_id,
                gizmo_type,
                conversation_template_id,
                conversation_origin,
                default_model_slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                title = excluded.title,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                source_json_path = excluded.source_json_path,
                source_mtime_ns = excluded.source_mtime_ns,
                docx_path = excluded.docx_path,
                indexed_at = excluded.indexed_at,
                primary_origin_type = excluded.primary_origin_type,
                primary_origin_id = excluded.primary_origin_id,
                gizmo_id = excluded.gizmo_id,
                gizmo_type = excluded.gizmo_type,
                conversation_template_id = excluded.conversation_template_id,
                conversation_origin = excluded.conversation_origin,
                default_model_slug = excluded.default_model_slug
            """,
            (
                conversation_id,
                title,
                iso_datetime(conversation.get("create_time")),
                iso_datetime(conversation.get("update_time")),
                str(json_path),
                source_mtime_ns,
                str(docx) if docx else None,
                indexed_at,
                primary_type,
                primary_id,
                optional_string(conversation.get("gizmo_id")),
                optional_string(conversation.get("gizmo_type")),
                optional_string(conversation.get("conversation_template_id")),
                optional_string(conversation.get("conversation_origin")),
                optional_string(conversation.get("default_model_slug")),
            ),
        )

        delete_message_index_rows(connection, conversation_id)
        replace_detected_origins(connection, conversation_id, origins, primary_id)

        for position, message in enumerate(visible_messages, start=1):
            body = extract_message_text(message)
            message_id = message.get("id", f"message-{position}")
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id,
                    message_id,
                    message_order,
                    author_role,
                    created_at,
                    content_type,
                    body
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    message_id,
                    position,
                    message.get("author", {}).get("role", "unknown"),
                    iso_datetime(message.get("create_time")),
                    message.get("content", {}).get("content_type"),
                    body,
                ),
            )
            connection.execute(
                """
                INSERT INTO messages_fts (
                    rowid,
                    body,
                    title,
                    conversation_id,
                    message_id,
                    author_role
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    body,
                    title,
                    conversation_id,
                    message_id,
                    message.get("author", {}).get("role", "unknown"),
                ),
            )

    LOGGER.info(
        "Indexed %s (%d visible messages, origin=%s%s)",
        json_path.name,
        len(visible_messages),
        primary_type,
        f":{primary_id}" if primary_id else "",
    )
    if not docx:
        LOGGER.warning("No associated DOCX found for %s", conversation_id)
    return True


def build_index(
    downloads_dir: Path,
    archive_root: Path,
    database_path: Path,
    *,
    force: bool = False,
) -> None:
    """Index every .json.xz file under downloads."""
    if not downloads_dir.is_dir():
        raise FileNotFoundError(
            f"Downloads directory does not exist: {downloads_dir}"
        )

    database_path.parent.mkdir(parents=True, exist_ok=True)
    json_files = sorted(downloads_dir.rglob("*.json.xz"))
    LOGGER.info("Found %d compressed conversation JSON files", len(json_files))
    if not json_files:
        return

    indexed = 0
    failed = 0
    with connect_database(database_path) as connection:
        for json_path in json_files:
            try:
                indexed += int(
                    index_one(
                        connection,
                        json_path,
                        archive_root,
                        force=force,
                    )
                )
            except (
                OSError,
                ValueError,
                json.JSONDecodeError,
                lzma.LZMAError,
            ) as error:
                failed += 1
                LOGGER.exception("Could not index %s: %s", json_path, error)

    LOGGER.info(
        "Index complete: %d updated, %d unchanged or skipped, %d failed",
        indexed,
        len(json_files) - indexed - failed,
        failed,
    )
    LOGGER.info("Database: %s", database_path)


def rebuild_index(
    downloads_dir: Path, archive_root: Path, database_path: Path
) -> None:
    """Delete the disposable index database and rebuild it from source exports."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    remove_database_files(database_path)
    build_index(
        downloads_dir,
        archive_root,
        database_path,
        force=True,
    )


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------


def search_terms(user_query: str) -> list[str]:
    """Return unique literal search terms, retaining punctuation such as hyphens."""
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in user_query.split():
        term = raw_term.strip('"')
        normalized = term.casefold()
        if term and normalized not in seen:
            seen.add(normalized)
            terms.append(term)
    return terms


def make_fts_query(user_query: str) -> str:
    """Turn a plain-language query into safe FTS5 body terms."""
    terms = search_terms(user_query)
    if not terms:
        raise ValueError(
            "Search query must contain at least one non-space character."
        )
    joined_terms = " AND ".join(
        f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms
    )
    return f"body : ({joined_terms})"


def highlight_terms(text: str, user_query: str) -> str:
    """Mark literal search terms in an output excerpt without changing content."""
    terms = search_terms(user_query)
    if not terms:
        return text
    pattern = re.compile(
        "|".join(re.escape(term) for term in terms), re.IGNORECASE
    )
    return pattern.sub(lambda match: f"[{match.group(0)}]", text)


def resolve_origin_filter(
    connection: sqlite3.Connection, selector: str
) -> list[str]:
    """Resolve an origin ID, exact label, or unique ID prefix."""
    rows = connection.execute(
        """
        SELECT origin_id
        FROM origins
        WHERE origin_id = ?
           OR origin_id LIKE ?
           OR label = ? COLLATE NOCASE
        ORDER BY origin_id
        """,
        (selector, selector + "%", selector),
    ).fetchall()
    ids = sorted({row["origin_id"] for row in rows})
    if not ids:
        raise ValueError(f"Unknown origin: {selector}")
    if len(ids) > 1:
        raise ValueError(
            f"Ambiguous origin selector '{selector}': {', '.join(ids)}"
        )
    return ids


def matching_rows(
    database_path: Path,
    query: str,
    *,
    category: str | None = None,
    tag: str | None = None,
    project: str | None = None,
    origin: str | None = None,
) -> list[sqlite3.Row]:
    """Return every message matching the query and optional filters."""
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Index does not exist: {database_path}. Run 'index' first."
        )

    with connect_database(database_path) as connection:
        conditions = ["messages_fts MATCH ?"]
        parameters: list[Any] = [make_fts_query(query)]

        if category:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_categories AS cc
                    JOIN categories AS cat ON cat.category_id = cc.category_id
                    WHERE cc.conversation_id = c.conversation_id
                      AND cat.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(category)

        if tag:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_tags AS ct
                    JOIN tags AS t ON t.tag_id = ct.tag_id
                    WHERE ct.conversation_id = c.conversation_id
                      AND t.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(tag)

        if project:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_work_projects AS cwp
                    JOIN work_projects AS wp ON wp.project_id = cwp.project_id
                    WHERE cwp.conversation_id = c.conversation_id
                      AND wp.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(project)

        if origin:
            origin_ids = resolve_origin_filter(connection, origin)
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_origins AS co
                    WHERE co.conversation_id = c.conversation_id
                      AND co.origin_id = ?
                )
                """
            )
            parameters.append(origin_ids[0])

        sql = f"""
            SELECT
                c.conversation_id,
                c.title,
                c.created_at,
                c.updated_at,
                c.docx_path,
                c.primary_origin_type,
                c.primary_origin_id,
                m.author_role,
                m.message_order,
                m.body,
                bm25(messages_fts) AS rank
            FROM messages_fts
            JOIN messages AS m ON m.id = messages_fts.rowid
            JOIN conversations AS c ON c.conversation_id = m.conversation_id
            WHERE {' AND '.join(conditions)}
        """
        return connection.execute(sql, parameters).fetchall()


def title_matches_query(title: str, query: str) -> bool:
    """Return True when every literal search term appears in the title."""
    terms = search_terms(query)
    if not terms:
        return False
    folded_title = title.casefold()
    return all(term.casefold() in folded_title for term in terms)


def classification_candidates(
    database_path: Path, query: str
) -> list[dict[str, Any]]:
    """Build per-conversation relevance statistics for a literal FTS query.

    Body matches come from the FTS index. Title-only matches are added even
    when the body does not match, because a literal title match is strong
    evidence that the conversation is genuinely about the requested topic.
    """
    rows = matching_rows(database_path, query)
    terms = search_terms(query)
    documents: dict[str, dict[str, Any]] = {}

    for row in rows:
        document = documents.setdefault(
            row["conversation_id"],
            {
                "conversation_id": row["conversation_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "occurrences": 0,
                "matching_messages": 0,
                "best_rank": row["rank"],
                "title_match": title_matches_query(row["title"], query),
            },
        )
        document["occurrences"] += sum(
            len(re.findall(re.escape(term), row["body"], flags=re.IGNORECASE))
            for term in terms
        )
        document["matching_messages"] += 1
        document["best_rank"] = min(document["best_rank"], row["rank"])

    with connect_database(database_path) as connection:
        title_rows = connection.execute(
            "SELECT conversation_id, title, created_at FROM conversations"
        ).fetchall()

    for row in title_rows:
        if not title_matches_query(row["title"], query):
            continue
        documents.setdefault(
            row["conversation_id"],
            {
                "conversation_id": row["conversation_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "occurrences": 0,
                "matching_messages": 0,
                "best_rank": None,
                "title_match": True,
            },
        )["title_match"] = True

    return sorted(
        documents.values(),
        key=lambda document: (
            not document["title_match"],
            -document["occurrences"],
            -document["matching_messages"],
            document["best_rank"] if document["best_rank"] is not None else 0.0,
            document["title"].casefold(),
        ),
    )


def candidate_is_relevant(
    candidate: dict[str, Any],
    *,
    title_only: bool,
    min_occurrences: int,
    min_messages: int,
) -> bool:
    """Apply conservative relevance rules to one search candidate."""
    if title_only:
        return bool(candidate["title_match"])
    return bool(candidate["title_match"]) or (
        candidate["occurrences"] >= min_occurrences
        and candidate["matching_messages"] >= min_messages
    )


def selected_classification_candidates(
    database_path: Path,
    query: str,
    *,
    title_only: bool,
    min_occurrences: int,
    min_messages: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return all candidates plus those passing the relevance threshold."""
    if min_occurrences < 1:
        raise ValueError("--min-occurrences must be at least 1.")
    if min_messages < 1:
        raise ValueError("--min-messages must be at least 1.")

    candidates = classification_candidates(database_path, query)
    selected = [
        candidate
        for candidate in candidates
        if candidate_is_relevant(
            candidate,
            title_only=title_only,
            min_occurrences=min_occurrences,
            min_messages=min_messages,
        )
    ]
    return candidates, selected


def print_classification_suggestions(
    database_path: Path,
    query: str,
    *,
    title_only: bool,
    min_occurrences: int,
    min_messages: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Print relevance evidence and return the candidates selected by policy."""
    candidates, selected = selected_classification_candidates(
        database_path,
        query,
        title_only=title_only,
        min_occurrences=min_occurrences,
        min_messages=min_messages,
    )
    selected_ids = {candidate["conversation_id"] for candidate in selected}

    if not candidates:
        print("No matching conversations.")
        return []

    shown = candidates[:limit]
    for number, candidate in enumerate(shown, start=1):
        selected_flag = candidate["conversation_id"] in selected_ids
        if candidate["title_match"]:
            reason = "title match"
        elif selected_flag:
            reason = "thresholds met"
        else:
            reason = "weak reference"

        print(f"\n{number}. {candidate['title']}")
        print(f"   ID: {candidate['conversation_id']}")
        print(f"   Title match: {'yes' if candidate['title_match'] else 'no'}")
        print(
            "   References: "
            f"{candidate['occurrences']} occurrences in "
            f"{candidate['matching_messages']} messages"
        )
        print(f"   Suggested: {'YES' if selected_flag else 'no'} ({reason})")

    if len(candidates) > limit:
        print(f"\n... {len(candidates) - limit} additional candidate(s) not shown.")

    print(
        f"\nSelected by policy: {len(selected)} of {len(candidates)} candidate(s)."
    )
    if title_only:
        print("Policy: title match only.")
    else:
        print(
            "Policy: title match OR at least "
            f"{min_occurrences} occurrences across "
            f"{min_messages} matching messages."
        )
    return selected


def search_documents(
    database_path: Path,
    query: str,
    limit: int,
    *,
    category: str | None = None,
    tag: str | None = None,
    project: str | None = None,
    origin: str | None = None,
) -> None:
    """Rank matching conversations by literal query references."""
    rows = matching_rows(
        database_path,
        query,
        category=category,
        tag=tag,
        project=project,
        origin=origin,
    )
    if not rows:
        print("No results.")
        return

    terms = search_terms(query)
    documents: dict[str, dict[str, Any]] = {}
    for row in rows:
        document = documents.setdefault(
            row["conversation_id"],
            {
                "conversation_id": row["conversation_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "docx_path": row["docx_path"],
                "origin_type": row["primary_origin_type"],
                "origin_id": row["primary_origin_id"],
                "occurrences": 0,
                "matching_messages": 0,
                "best_rank": row["rank"],
            },
        )
        document["occurrences"] += sum(
            len(re.findall(re.escape(term), row["body"], flags=re.IGNORECASE))
            for term in terms
        )
        document["matching_messages"] += 1
        document["best_rank"] = min(document["best_rank"], row["rank"])

    ranked_documents = sorted(
        documents.values(),
        key=lambda document: (
            -document["occurrences"],
            -document["matching_messages"],
            document["best_rank"],
            document["title"].casefold(),
        ),
    )[:limit]

    for number, document in enumerate(ranked_documents, start=1):
        print(f"\n{number}. {document['title']}")
        print(f"   ID: {document['conversation_id']}")
        print(
            "   References: "
            f"{document['occurrences']} occurrences in "
            f"{document['matching_messages']} messages"
        )
        print(f"   Created: {document['created_at'] or 'unknown'}")
        print(
            "   Origin: "
            f"{document['origin_type']}"
            + (f" ({document['origin_id']})" if document["origin_id"] else "")
        )
        print(f"   DOCX: {document['docx_path'] or 'not found'}")


def search_messages(
    database_path: Path,
    query: str,
    limit: int,
    *,
    category: str | None = None,
    tag: str | None = None,
    project: str | None = None,
    origin: str | None = None,
) -> None:
    """Show individual matching messages and excerpts."""
    rows = sorted(
        matching_rows(
            database_path,
            query,
            category=category,
            tag=tag,
            project=project,
            origin=origin,
        ),
        key=lambda row: row["rank"],
    )[:limit]
    if not rows:
        print("No results.")
        return

    for number, row in enumerate(rows, start=1):
        print(f"\n{number}. {row['title']}")
        print(f"   ID: {row['conversation_id']}")
        print(f"   Created: {row['created_at'] or 'unknown'}")
        print(f"   Message: {row['message_order']} ({row['author_role']})")
        print(f"   DOCX: {row['docx_path'] or 'not found'}")
        excerpt = highlight_terms(row["body"], query)
        if len(excerpt) > 700:
            excerpt = excerpt[:700] + "…"
        print(f"   Excerpt: {excerpt}")


# ---------------------------------------------------------------------------
# Categories, tags, origins, listing and inspection
# ---------------------------------------------------------------------------


def resolve_conversation(
    connection: sqlite3.Connection, selector: str
) -> sqlite3.Row:
    """Resolve a conversation by full ID, unique ID prefix, or exact title."""
    rows = connection.execute(
        """
        SELECT conversation_id, title
        FROM conversations
        WHERE conversation_id = ?
           OR conversation_id LIKE ?
           OR title = ? COLLATE NOCASE
        ORDER BY created_at DESC
        """,
        (selector, selector + "%", selector),
    ).fetchall()

    unique: dict[str, sqlite3.Row] = {
        row["conversation_id"]: row for row in rows
    }
    rows = list(unique.values())

    if not rows:
        raise ValueError(f"Conversation not found: {selector}")
    if len(rows) > 1:
        detail = "; ".join(
            f"{row['conversation_id'][:8]}… {row['title']}" for row in rows
        )
        raise ValueError(f"Ambiguous conversation selector '{selector}': {detail}")
    return rows[0]


def get_or_create_category(
    connection: sqlite3.Connection, name: str
) -> sqlite3.Row:
    """Return a category row, creating it when needed."""
    clean_name = normalize_text(name)
    if not clean_name:
        raise ValueError("Category name cannot be empty.")

    row = connection.execute(
        "SELECT category_id, name FROM categories WHERE name = ? COLLATE NOCASE",
        (clean_name,),
    ).fetchone()
    if row:
        return row

    with connection:
        cursor = connection.execute(
            "INSERT INTO categories (name, description, created_at) VALUES (?, NULL, ?)",
            (clean_name, now_iso()),
        )
    return connection.execute(
        "SELECT category_id, name FROM categories WHERE category_id = ?",
        (cursor.lastrowid,),
    ).fetchone()


def add_category_to_conversation(
    database_path: Path, conversation_selector: str, category_name: str
) -> None:
    """Assign one category to one conversation."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        category = get_or_create_category(connection, category_name)
        with connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO conversation_categories (
                    conversation_id, category_id, assigned_at
                ) VALUES (?, ?, ?)
                """,
                (
                    conversation["conversation_id"],
                    category["category_id"],
                    now_iso(),
                ),
            )
        print(
            f"Category '{category['name']}' assigned to "
            f"'{conversation['title']}'."
        )


def remove_category_from_conversation(
    database_path: Path, conversation_selector: str, category_name: str
) -> None:
    """Remove one category from one conversation."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        with connection:
            cursor = connection.execute(
                """
                DELETE FROM conversation_categories
                WHERE conversation_id = ?
                  AND category_id = (
                      SELECT category_id
                      FROM categories
                      WHERE name = ? COLLATE NOCASE
                  )
                """,
                (conversation["conversation_id"], category_name),
            )
        if cursor.rowcount:
            print(
                f"Category '{category_name}' removed from "
                f"'{conversation['title']}'."
            )
        else:
            print("No matching category assignment was found.")


def bulk_add_category_from_search(
    database_path: Path,
    category_name: str,
    query: str,
    *,
    title_only: bool,
    min_occurrences: int,
    min_messages: int,
    apply: bool,
    limit: int,
) -> None:
    """Preview or apply a category to conservatively selected conversations."""
    selected = print_classification_suggestions(
        database_path,
        query,
        title_only=title_only,
        min_occurrences=min_occurrences,
        min_messages=min_messages,
        limit=limit,
    )
    if not selected:
        print("No conversations selected; nothing changed.")
        return

    print(f"Target category: {category_name}")
    if not apply:
        print("Preview only: no database changes were made. Re-run with --apply to write.")
        return

    with connect_database(database_path) as connection:
        category = get_or_create_category(connection, category_name)
        added = 0
        with connection:
            for candidate in selected:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO conversation_categories (
                        conversation_id, category_id, assigned_at
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        candidate["conversation_id"],
                        category["category_id"],
                        now_iso(),
                    ),
                )
                added += max(cursor.rowcount, 0)

    print(
        f"Category '{category_name}' selected for {len(selected)} conversation(s); "
        f"{added} new assignment(s) written."
    )


def clear_category_assignments(
    database_path: Path, category_name: str, *, apply: bool, limit: int
) -> None:
    """Preview or remove every assignment of one category."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.title
            FROM conversation_categories AS cc
            JOIN categories AS cat ON cat.category_id = cc.category_id
            JOIN conversations AS c ON c.conversation_id = cc.conversation_id
            WHERE cat.name = ? COLLATE NOCASE
            ORDER BY c.created_at DESC, c.title COLLATE NOCASE
            """,
            (category_name,),
        ).fetchall()

        if not rows:
            print(f"Category '{category_name}' has no conversation assignments.")
            return

        for number, row in enumerate(rows[:limit], start=1):
            print(f"{number}. {row['title']} ({row['conversation_id']})")
        if len(rows) > limit:
            print(f"... {len(rows) - limit} additional assignment(s) not shown.")

        print(f"\nAssignments found: {len(rows)}")
        if not apply:
            print("Preview only: nothing removed. Re-run with --apply to remove them.")
            return

        with connection:
            cursor = connection.execute(
                """
                DELETE FROM conversation_categories
                WHERE category_id = (
                    SELECT category_id
                    FROM categories
                    WHERE name = ? COLLATE NOCASE
                )
                """,
                (category_name,),
            )
        print(f"Removed {cursor.rowcount} assignment(s) for category '{category_name}'.")


def list_categories(database_path: Path) -> None:
    """List categories and conversation counts."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                cat.name,
                cat.description,
                COUNT(cc.conversation_id) AS conversation_count
            FROM categories AS cat
            LEFT JOIN conversation_categories AS cc
                ON cc.category_id = cat.category_id
            GROUP BY cat.category_id
            ORDER BY cat.name COLLATE NOCASE
            """
        ).fetchall()

    if not rows:
        print("No categories defined.")
        return

    for row in rows:
        print(f"{row['name']}: {row['conversation_count']} conversation(s)")


def get_or_create_tag(
    connection: sqlite3.Connection, name: str
) -> sqlite3.Row:
    """Return a tag row, creating it when needed."""
    clean_name = normalize_text(name)
    if not clean_name:
        raise ValueError("Tag name cannot be empty.")

    row = connection.execute(
        "SELECT tag_id, name FROM tags WHERE name = ? COLLATE NOCASE",
        (clean_name,),
    ).fetchone()
    if row:
        return row

    with connection:
        cursor = connection.execute(
            "INSERT INTO tags (name, description, created_at) VALUES (?, NULL, ?)",
            (clean_name, now_iso()),
        )
    return connection.execute(
        "SELECT tag_id, name FROM tags WHERE tag_id = ?",
        (cursor.lastrowid,),
    ).fetchone()


def add_tag_to_conversation(
    database_path: Path, conversation_selector: str, tag_name: str
) -> None:
    """Assign one tag to one conversation."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        tag = get_or_create_tag(connection, tag_name)
        with connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO conversation_tags (
                    conversation_id, tag_id, assigned_at
                ) VALUES (?, ?, ?)
                """,
                (
                    conversation["conversation_id"],
                    tag["tag_id"],
                    now_iso(),
                ),
            )
        print(f"Tag '{tag['name']}' assigned to '{conversation['title']}'.")


def remove_tag_from_conversation(
    database_path: Path, conversation_selector: str, tag_name: str
) -> None:
    """Remove one tag from one conversation."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        with connection:
            cursor = connection.execute(
                """
                DELETE FROM conversation_tags
                WHERE conversation_id = ?
                  AND tag_id = (
                      SELECT tag_id
                      FROM tags
                      WHERE name = ? COLLATE NOCASE
                  )
                """,
                (conversation["conversation_id"], tag_name),
            )
        if cursor.rowcount:
            print(f"Tag '{tag_name}' removed from '{conversation['title']}'.")
        else:
            print("No matching tag assignment was found.")


def bulk_add_tag_from_search(
    database_path: Path,
    tag_name: str,
    query: str,
    *,
    title_only: bool,
    min_occurrences: int,
    min_messages: int,
    apply: bool,
    limit: int,
) -> None:
    """Preview or apply a tag to conservatively selected conversations."""
    selected = print_classification_suggestions(
        database_path,
        query,
        title_only=title_only,
        min_occurrences=min_occurrences,
        min_messages=min_messages,
        limit=limit,
    )
    if not selected:
        print("No conversations selected; nothing changed.")
        return

    print(f"Target tag: {tag_name}")
    if not apply:
        print("Preview only: no database changes were made. Re-run with --apply to write.")
        return

    with connect_database(database_path) as connection:
        tag = get_or_create_tag(connection, tag_name)
        added = 0
        with connection:
            for candidate in selected:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO conversation_tags (
                        conversation_id, tag_id, assigned_at
                    ) VALUES (?, ?, ?)
                    """,
                    (
                        candidate["conversation_id"],
                        tag["tag_id"],
                        now_iso(),
                    ),
                )
                added += max(cursor.rowcount, 0)

    print(
        f"Tag '{tag_name}' selected for {len(selected)} conversation(s); "
        f"{added} new assignment(s) written."
    )


def clear_tag_assignments(
    database_path: Path, tag_name: str, *, apply: bool, limit: int
) -> None:
    """Preview or remove every assignment of one tag."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT c.conversation_id, c.title
            FROM conversation_tags AS ct
            JOIN tags AS t ON t.tag_id = ct.tag_id
            JOIN conversations AS c ON c.conversation_id = ct.conversation_id
            WHERE t.name = ? COLLATE NOCASE
            ORDER BY c.created_at DESC, c.title COLLATE NOCASE
            """,
            (tag_name,),
        ).fetchall()

        if not rows:
            print(f"Tag '{tag_name}' has no conversation assignments.")
            return

        for number, row in enumerate(rows[:limit], start=1):
            print(f"{number}. {row['title']} ({row['conversation_id']})")
        if len(rows) > limit:
            print(f"... {len(rows) - limit} additional assignment(s) not shown.")

        print(f"\nAssignments found: {len(rows)}")
        if not apply:
            print("Preview only: nothing removed. Re-run with --apply to remove them.")
            return

        with connection:
            cursor = connection.execute(
                """
                DELETE FROM conversation_tags
                WHERE tag_id = (
                    SELECT tag_id
                    FROM tags
                    WHERE name = ? COLLATE NOCASE
                )
                """,
                (tag_name,),
            )
        print(f"Removed {cursor.rowcount} assignment(s) for tag '{tag_name}'.")


def list_tags(database_path: Path) -> None:
    """List tags and conversation counts."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                t.name,
                t.description,
                COUNT(ct.conversation_id) AS conversation_count
            FROM tags AS t
            LEFT JOIN conversation_tags AS ct ON ct.tag_id = t.tag_id
            GROUP BY t.tag_id
            ORDER BY t.name COLLATE NOCASE
            """
        ).fetchall()

    if not rows:
        print("No tags defined.")
        return

    for row in rows:
        print(f"{row['name']}: {row['conversation_count']} conversation(s)")


def list_origins(database_path: Path) -> None:
    """List detected native origins and their conversation counts."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                o.origin_id,
                o.origin_type,
                o.label,
                COUNT(co.conversation_id) AS conversation_count
            FROM origins AS o
            LEFT JOIN conversation_origins AS co ON co.origin_id = o.origin_id
            GROUP BY o.origin_id
            ORDER BY o.origin_type, COALESCE(o.label, o.origin_id) COLLATE NOCASE
            """
        ).fetchall()

        standard_count = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM conversations AS c
            WHERE NOT EXISTS (
                SELECT 1
                FROM conversation_origins AS co
                WHERE co.conversation_id = c.conversation_id
            )
            """
        ).fetchone()["n"]

    print(f"standard: {standard_count} conversation(s)")
    for row in rows:
        label = f" — {row['label']}" if row["label"] else ""
        print(
            f"{row['origin_type']}: {row['origin_id']}"
            f"{label} ({row['conversation_count']} conversation(s))"
        )


def set_origin_label(database_path: Path, selector: str, label: str) -> None:
    """Assign or clear a human label for one opaque native origin ID."""
    clean_label = normalize_text(label)
    with connect_database(database_path) as connection:
        origin_ids = resolve_origin_filter(connection, selector)
        with connection:
            connection.execute(
                "UPDATE origins SET label = ? WHERE origin_id = ?",
                (clean_label or None, origin_ids[0]),
            )
        print(
            f"Origin {origin_ids[0]} label set to "
            f"{clean_label!r}."
        )


def get_or_create_work_project(
    connection: sqlite3.Connection, name: str
) -> sqlite3.Row:
    """Return a work-project row, creating it when needed."""
    clean_name = normalize_text(name)
    if not clean_name:
        raise ValueError("Project name cannot be empty.")

    row = connection.execute(
        "SELECT project_id, name FROM work_projects WHERE name = ? COLLATE NOCASE",
        (clean_name,),
    ).fetchone()
    if row:
        return row

    with connection:
        cursor = connection.execute(
            "INSERT INTO work_projects (name, description, created_at) VALUES (?, NULL, ?)",
            (clean_name, now_iso()),
        )
    return connection.execute(
        "SELECT project_id, name FROM work_projects WHERE project_id = ?",
        (cursor.lastrowid,),
    ).fetchone()


def add_work_project_to_conversation(
    database_path: Path, conversation_selector: str, project_name: str
) -> None:
    """Assign one conversation to one user-defined work project."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        project = get_or_create_work_project(connection, project_name)
        with connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO conversation_work_projects (
                    conversation_id, project_id, assigned_at
                ) VALUES (?, ?, ?)
                """,
                (
                    conversation["conversation_id"],
                    project["project_id"],
                    now_iso(),
                ),
            )
        print(f"Project '{project['name']}' assigned to '{conversation['title']}'.")


def remove_work_project_from_conversation(
    database_path: Path, conversation_selector: str, project_name: str
) -> None:
    """Remove one work-project assignment from one conversation."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, conversation_selector)
        with connection:
            cursor = connection.execute(
                """
                DELETE FROM conversation_work_projects
                WHERE conversation_id = ?
                  AND project_id = (
                      SELECT project_id
                      FROM work_projects
                      WHERE name = ? COLLATE NOCASE
                  )
                """,
                (conversation["conversation_id"], project_name),
            )
        if cursor.rowcount:
            print(f"Project '{project_name}' removed from '{conversation['title']}'.")
        else:
            print("No matching project assignment was found.")


def rename_work_project(
    database_path: Path, current_name: str, new_name: str
) -> None:
    """Rename one user-defined work project."""
    clean_name = normalize_text(new_name)
    if not clean_name:
        raise ValueError("New project name cannot be empty.")

    with connect_database(database_path) as connection:
        row = connection.execute(
            "SELECT project_id, name FROM work_projects WHERE name = ? COLLATE NOCASE",
            (current_name,),
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown project: {current_name}")

        duplicate = connection.execute(
            "SELECT project_id FROM work_projects WHERE name = ? COLLATE NOCASE",
            (clean_name,),
        ).fetchone()
        if duplicate and duplicate["project_id"] != row["project_id"]:
            raise ValueError(f"A project named '{clean_name}' already exists.")

        with connection:
            connection.execute(
                "UPDATE work_projects SET name = ? WHERE project_id = ?",
                (clean_name, row["project_id"]),
            )
        print(f"Project '{row['name']}' renamed to '{clean_name}'.")


def list_work_projects(database_path: Path) -> None:
    """Print the concise list of user-defined work projects and counts."""
    with connect_database(database_path) as connection:
        rows = connection.execute(
            """
            SELECT
                wp.name,
                COUNT(cwp.conversation_id) AS conversation_count
            FROM work_projects AS wp
            LEFT JOIN conversation_work_projects AS cwp
                ON cwp.project_id = wp.project_id
            GROUP BY wp.project_id
            ORDER BY wp.name COLLATE NOCASE
            """
        ).fetchall()

    if not rows:
        print("No projects defined.")
        return

    for row in rows:
        print(f"{row['name']}: {row['conversation_count']} conversation(s)")


def show_work_project(database_path: Path, project_name: str) -> None:
    """Show all conversations assigned to one user-defined work project."""
    with connect_database(database_path) as connection:
        project = connection.execute(
            "SELECT project_id, name, description FROM work_projects WHERE name = ? COLLATE NOCASE",
            (project_name,),
        ).fetchone()
        if not project:
            raise ValueError(f"Unknown project: {project_name}")

        rows = connection.execute(
            """
            SELECT
                c.conversation_id,
                c.title,
                c.created_at,
                c.primary_origin_type,
                c.primary_origin_id,
                o.label AS origin_label
            FROM conversation_work_projects AS cwp
            JOIN conversations AS c ON c.conversation_id = cwp.conversation_id
            LEFT JOIN origins AS o ON o.origin_id = c.primary_origin_id
            WHERE cwp.project_id = ?
            ORDER BY c.created_at DESC, c.title COLLATE NOCASE
            """,
            (project["project_id"],),
        ).fetchall()

    print(f"Project: {project['name']}")
    print(f"Conversations: {len(rows)}")
    if not rows:
        return

    for number, row in enumerate(rows, start=1):
        date = (row["created_at"] or "unknown")[:10]
        origin_display = row["primary_origin_type"]
        if row["primary_origin_id"]:
            origin_name = row["origin_label"] or row["primary_origin_id"]
            origin_display += f": {origin_name}"
        print(f"{number}. {date} | {row['title']}")
        print(f"   Origin: {origin_display}")
        print(f"   ID: {row['conversation_id']}")


def list_conversations(
    database_path: Path,
    *,
    category: str | None,
    tag: str | None,
    project: str | None,
    origin: str | None,
    uncategorized: bool,
    untagged: bool,
    unprojected: bool,
    sort: str,
    limit: int,
) -> None:
    """List conversations with projects, categories, tags and native origin labels."""
    with connect_database(database_path) as connection:
        conditions: list[str] = []
        parameters: list[Any] = []

        if category:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_categories AS cc2
                    JOIN categories AS cat2 ON cat2.category_id = cc2.category_id
                    WHERE cc2.conversation_id = c.conversation_id
                      AND cat2.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(category)

        if tag:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_tags AS ct2
                    JOIN tags AS t2 ON t2.tag_id = ct2.tag_id
                    WHERE ct2.conversation_id = c.conversation_id
                      AND t2.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(tag)

        if project:
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_work_projects AS cwp2
                    JOIN work_projects AS wp2 ON wp2.project_id = cwp2.project_id
                    WHERE cwp2.conversation_id = c.conversation_id
                      AND wp2.name = ? COLLATE NOCASE
                )
                """
            )
            parameters.append(project)

        if uncategorized:
            conditions.append(
                """
                NOT EXISTS (
                    SELECT 1
                    FROM conversation_categories AS cc3
                    WHERE cc3.conversation_id = c.conversation_id
                )
                """
            )

        if untagged:
            conditions.append(
                """
                NOT EXISTS (
                    SELECT 1
                    FROM conversation_tags AS ct3
                    WHERE ct3.conversation_id = c.conversation_id
                )
                """
            )

        if unprojected:
            conditions.append(
                """
                NOT EXISTS (
                    SELECT 1
                    FROM conversation_work_projects AS cwp3
                    WHERE cwp3.conversation_id = c.conversation_id
                )
                """
            )

        if origin:
            origin_ids = resolve_origin_filter(connection, origin)
            conditions.append(
                """
                EXISTS (
                    SELECT 1
                    FROM conversation_origins AS co2
                    WHERE co2.conversation_id = c.conversation_id
                      AND co2.origin_id = ?
                )
                """
            )
            parameters.append(origin_ids[0])

        order_by = {
            "date": "c.created_at DESC, c.title COLLATE NOCASE",
            "title": "c.title COLLATE NOCASE, c.created_at DESC",
            "origin": "c.primary_origin_type, COALESCE(o.label, c.primary_origin_id, ''), c.title COLLATE NOCASE",
        }[sort]

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        sql = f"""
            SELECT
                c.conversation_id,
                c.title,
                c.created_at,
                c.primary_origin_type,
                c.primary_origin_id,
                o.label AS origin_label,
                GROUP_CONCAT(DISTINCT wp.name) AS projects,
                GROUP_CONCAT(DISTINCT cat.name) AS categories,
                GROUP_CONCAT(DISTINCT t.name) AS tags
            FROM conversations AS c
            LEFT JOIN origins AS o ON o.origin_id = c.primary_origin_id
            LEFT JOIN conversation_work_projects AS cwp
                ON cwp.conversation_id = c.conversation_id
            LEFT JOIN work_projects AS wp ON wp.project_id = cwp.project_id
            LEFT JOIN conversation_categories AS cc
                ON cc.conversation_id = c.conversation_id
            LEFT JOIN categories AS cat ON cat.category_id = cc.category_id
            LEFT JOIN conversation_tags AS ct
                ON ct.conversation_id = c.conversation_id
            LEFT JOIN tags AS t ON t.tag_id = ct.tag_id
            {where_sql}
            GROUP BY c.conversation_id
            ORDER BY {order_by}
            LIMIT ?
        """
        parameters.append(limit)
        rows = connection.execute(sql, parameters).fetchall()

    if not rows:
        print("No conversations.")
        return

    for number, row in enumerate(rows, start=1):
        date = (row["created_at"] or "unknown")[:10]
        origin_display = row["primary_origin_type"]
        if row["primary_origin_id"]:
            origin_name = row["origin_label"] or row["primary_origin_id"]
            origin_display += f": {origin_name}"
        projects = row["projects"] or "—"
        categories = row["categories"] or "—"
        tags = row["tags"] or "—"
        print(f"\n{number}. {date} | {row['title']}")
        print(f"   ID: {row['conversation_id']}")
        print(f"   Origin: {origin_display}")
        print(f"   Projects: {projects}")
        print(f"   Categories: {categories}")
        print(f"   Tags: {tags}")


def show_conversation(database_path: Path, selector: str) -> None:
    """Show metadata, projects, categories, tags and all detected native origins."""
    with connect_database(database_path) as connection:
        conversation = resolve_conversation(connection, selector)
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation["conversation_id"],),
        ).fetchone()
        project_rows = connection.execute(
            """
            SELECT wp.name
            FROM conversation_work_projects AS cwp
            JOIN work_projects AS wp ON wp.project_id = cwp.project_id
            WHERE cwp.conversation_id = ?
            ORDER BY wp.name COLLATE NOCASE
            """,
            (conversation["conversation_id"],),
        ).fetchall()
        category_rows = connection.execute(
            """
            SELECT cat.name
            FROM conversation_categories AS cc
            JOIN categories AS cat ON cat.category_id = cc.category_id
            WHERE cc.conversation_id = ?
            ORDER BY cat.name COLLATE NOCASE
            """,
            (conversation["conversation_id"],),
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT t.name
            FROM conversation_tags AS ct
            JOIN tags AS t ON t.tag_id = ct.tag_id
            WHERE ct.conversation_id = ?
            ORDER BY t.name COLLATE NOCASE
            """,
            (conversation["conversation_id"],),
        ).fetchall()
        origin_rows = connection.execute(
            """
            SELECT o.origin_type, o.origin_id, o.label, co.source, co.is_primary
            FROM conversation_origins AS co
            JOIN origins AS o ON o.origin_id = co.origin_id
            WHERE co.conversation_id = ?
            ORDER BY co.is_primary DESC, o.origin_type, o.origin_id
            """,
            (conversation["conversation_id"],),
        ).fetchall()

    print(f"Title: {row['title']}")
    print(f"ID: {row['conversation_id']}")
    print(f"Created: {row['created_at'] or 'unknown'}")
    print(f"Updated: {row['updated_at'] or 'unknown'}")
    print(f"Model: {row['default_model_slug'] or 'unknown'}")
    print(f"DOCX: {row['docx_path'] or 'not found'}")
    print(f"JSON: {row['source_json_path']}")
    print(f"Top-level gizmo_id: {row['gizmo_id'] or '—'}")
    print(f"Top-level gizmo_type: {row['gizmo_type'] or '—'}")
    print(f"Conversation template: {row['conversation_template_id'] or '—'}")
    print(f"Conversation origin: {row['conversation_origin'] or '—'}")
    print(
        "Projects: "
        + (", ".join(item["name"] for item in project_rows) if project_rows else "—")
    )
    print(
        "Categories: "
        + (", ".join(item["name"] for item in category_rows) if category_rows else "—")
    )
    print(
        "Tags: "
        + (", ".join(item["name"] for item in tag_rows) if tag_rows else "—")
    )
    if origin_rows:
        print("Origins:")
        for origin in origin_rows:
            primary = " [primary]" if origin["is_primary"] else ""
            label = f" — {origin['label']}" if origin["label"] else ""
            print(
                f"  {origin['origin_type']}: {origin['origin_id']}"
                f"{label}{primary}"
            )
            print(f"    source: {origin['source']}")
    else:
        print("Origins: standard ChatGPT")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def add_common_filters(parser: argparse.ArgumentParser) -> None:
    """Add optional category/tag/origin filters to search-like commands."""
    parser.add_argument(
        "--category",
        help="Only include conversations assigned to this exact category name.",
    )
    parser.add_argument(
        "--tag",
        help="Only include conversations assigned to this exact tag name.",
    )
    parser.add_argument(
        "--project",
        help="Only include conversations assigned to this exact work project name.",
    )
    parser.add_argument(
        "--origin",
        help="Only include one native origin (ID, unique ID prefix, or exact label).",
    )


def add_relevance_policy_arguments(
    parser: argparse.ArgumentParser, *, include_apply: bool
) -> None:
    """Add conservative relevance controls for search-based classification."""
    parser.add_argument(
        "--title-only",
        action="store_true",
        help="Select only conversations whose title contains every query term.",
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=3,
        help=(
            "Minimum literal body occurrences when the title does not match "
            "(default: 3)."
        ),
    )
    parser.add_argument(
        "--min-messages",
        type=int,
        default=2,
        help=(
            "Minimum matching messages when the title does not match "
            "(default: 2)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum candidate rows shown in the preview (default: 100).",
    )
    if include_apply:
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the previewed assignments. Without this flag nothing changes.",
        )


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--debug", action="store_true", help="Enable verbose debug logging."
    )
    parser.add_argument(
        "--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT
    )
    parser.add_argument(
        "--downloads-dir", type=Path, default=DEFAULT_DOWNLOADS_DIR
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)

    commands = parser.add_subparsers(dest="command")

    index = commands.add_parser(
        "index", help="Create or incrementally update the full-text index."
    )
    index.add_argument(
        "--force",
        action="store_true",
        help="Re-index every source file without deleting manual categories or tags.",
    )

    commands.add_parser(
        "rebuild",
        help="Delete the SQLite index and recreate it from all .json.xz files.",
    )

    search = commands.add_parser(
        "search", help="Rank matching conversations by number of references."
    )
    search.add_argument("query", help='Search text, e.g. Migadu or "J-Trace Pro".')
    search.add_argument(
        "--limit", type=int, default=20, help="Maximum results (default: 20)."
    )
    add_common_filters(search)

    search_messages_parser = commands.add_parser(
        "search-messages",
        help="Show individual matching messages with excerpts.",
    )
    search_messages_parser.add_argument(
        "query", help='Search text, e.g. Migadu or "J-Trace Pro".'
    )
    search_messages_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum results (default: 20)."
    )
    add_common_filters(search_messages_parser)

    list_parser = commands.add_parser(
        "list", help="List conversations with origin and category information."
    )
    list_parser.add_argument(
        "--category", help="Only conversations in this exact category."
    )
    list_parser.add_argument(
        "--tag", help="Only conversations with this exact tag."
    )
    list_parser.add_argument(
        "--project", help="Only conversations in this exact work project."
    )
    list_parser.add_argument(
        "--origin", help="Origin ID, unique ID prefix, or exact label."
    )
    list_parser.add_argument(
        "--uncategorized",
        action="store_true",
        help="Only conversations with no assigned category.",
    )
    list_parser.add_argument(
        "--untagged",
        action="store_true",
        help="Only conversations with no assigned tag.",
    )
    list_parser.add_argument(
        "--unprojected",
        action="store_true",
        help="Only conversations with no assigned work project.",
    )
    list_parser.add_argument(
        "--sort",
        choices=("date", "title", "origin"),
        default="date",
        help="Sort order (default: date).",
    )
    list_parser.add_argument(
        "--limit", type=int, default=100, help="Maximum rows (default: 100)."
    )

    show = commands.add_parser(
        "show", help="Show one conversation's indexed metadata."
    )
    show.add_argument("conversation", help="Full/unique ID prefix or exact title.")

    commands.add_parser(
        "origins", help="List detected Custom GPT / Project origins."
    )

    origin_label = commands.add_parser(
        "origin-label", help="Assign a human label to an opaque origin ID."
    )
    origin_label.add_argument("origin", help="Origin ID, prefix, or exact label.")
    origin_label.add_argument(
        "label", help="Human label, e.g. 'Gandi GPT' or 'Relocation Project'."
    )

    commands.add_parser(
        "projects",
        help="List user-defined work projects and conversation counts.",
    )

    project_show = commands.add_parser(
        "project-show",
        help="Show conversations assigned to one work project.",
    )
    project_show.add_argument("project", help="Exact project name.")

    project_add = commands.add_parser(
        "project-add",
        help="Assign one conversation to a work project.",
    )
    project_add.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    project_add.add_argument("project", help="Project name; created if needed.")

    project_remove = commands.add_parser(
        "project-remove",
        help="Remove one work-project assignment from a conversation.",
    )
    project_remove.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    project_remove.add_argument("project", help="Exact project name.")

    project_rename = commands.add_parser(
        "project-rename",
        help="Rename one user-defined work project.",
    )
    project_rename.add_argument("project", help="Current exact project name.")
    project_rename.add_argument("new_name", help="New project name.")

    commands.add_parser("categories", help="List categories and counts.")

    category_add = commands.add_parser(
        "category-add", help="Assign a category to one conversation."
    )
    category_add.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    category_add.add_argument("category", help="Category name; created if needed.")

    category_remove = commands.add_parser(
        "category-remove", help="Remove a category from one conversation."
    )
    category_remove.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    category_remove.add_argument("category", help="Exact category name.")

    category_search = commands.add_parser(
        "category-add-search",
        help="Preview/apply a category to relevant search matches.",
    )
    category_search.add_argument("category", help="Category name; created if needed.")
    category_search.add_argument("query", help="Full-text query used to select conversations.")
    add_relevance_policy_arguments(category_search, include_apply=True)

    category_suggest = commands.add_parser(
        "category-suggest",
        help="Preview relevance evidence for category assignment without writing.",
    )
    category_suggest.add_argument("query", help="Full-text topic/query to evaluate.")
    add_relevance_policy_arguments(category_suggest, include_apply=False)

    category_clear = commands.add_parser(
        "category-clear",
        help="Preview/remove every assignment of one category.",
    )
    category_clear.add_argument("category", help="Exact category name.")
    category_clear.add_argument(
        "--apply",
        action="store_true",
        help="Remove the assignments. Without this flag nothing changes.",
    )
    category_clear.add_argument(
        "--limit", type=int, default=100, help="Maximum assignments shown (default: 100)."
    )

    commands.add_parser("tags", help="List tags and counts.")

    tag_add = commands.add_parser(
        "tag-add", help="Assign a tag to one conversation."
    )
    tag_add.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    tag_add.add_argument("tag", help="Tag name; created if needed.")

    tag_remove = commands.add_parser(
        "tag-remove", help="Remove a tag from one conversation."
    )
    tag_remove.add_argument(
        "conversation", help="Full/unique ID prefix or exact title."
    )
    tag_remove.add_argument("tag", help="Exact tag name.")

    tag_search = commands.add_parser(
        "tag-add-search",
        help="Preview/apply a tag to relevant search matches.",
    )
    tag_search.add_argument("tag", help="Tag name; created if needed.")
    tag_search.add_argument("query", help="Full-text query used to select conversations.")
    add_relevance_policy_arguments(tag_search, include_apply=True)

    tag_suggest = commands.add_parser(
        "tag-suggest",
        help="Preview relevance evidence for tag assignment without writing.",
    )
    tag_suggest.add_argument("query", help="Full-text topic/query to evaluate.")
    add_relevance_policy_arguments(tag_suggest, include_apply=False)

    tag_clear = commands.add_parser(
        "tag-clear",
        help="Preview/remove every assignment of one tag.",
    )
    tag_clear.add_argument("tag", help="Exact tag name.")
    tag_clear.add_argument(
        "--apply",
        action="store_true",
        help="Remove the assignments. Without this flag nothing changes.",
    )
    tag_clear.add_argument(
        "--limit", type=int, default=100, help="Maximum assignments shown (default: 100)."
    )

    # Defaults used when the script is launched without an explicit subcommand.
    # ``--force`` belongs to the ``index`` subparser, so argparse would otherwise
    # omit the attribute entirely when the implicit default command is used.
    parser.set_defaults(command="index", force=False)
    return parser


def main() -> int:
    """Run the selected command and return a process exit code."""
    parser = build_parser()
    arguments = parser.parse_args()
    configure_logging(arguments.debug)
    LOGGER.debug("Arguments: %s", arguments)

    try:
        if arguments.command == "index":
            build_index(
                arguments.downloads_dir,
                arguments.archive_root,
                arguments.database,
                force=arguments.force,
            )
        elif arguments.command == "rebuild":
            rebuild_index(
                arguments.downloads_dir,
                arguments.archive_root,
                arguments.database,
            )
        elif arguments.command == "search":
            search_documents(
                arguments.database,
                arguments.query,
                arguments.limit,
                category=arguments.category,
                tag=arguments.tag,
                project=arguments.project,
                origin=arguments.origin,
            )
        elif arguments.command == "search-messages":
            search_messages(
                arguments.database,
                arguments.query,
                arguments.limit,
                category=arguments.category,
                tag=arguments.tag,
                project=arguments.project,
                origin=arguments.origin,
            )
        elif arguments.command == "list":
            list_conversations(
                arguments.database,
                category=arguments.category,
                tag=arguments.tag,
                project=arguments.project,
                origin=arguments.origin,
                uncategorized=arguments.uncategorized,
                untagged=arguments.untagged,
                unprojected=arguments.unprojected,
                sort=arguments.sort,
                limit=arguments.limit,
            )
        elif arguments.command == "show":
            show_conversation(arguments.database, arguments.conversation)
        elif arguments.command == "origins":
            list_origins(arguments.database)
        elif arguments.command == "origin-label":
            set_origin_label(arguments.database, arguments.origin, arguments.label)
        elif arguments.command == "projects":
            list_work_projects(arguments.database)
        elif arguments.command == "project-show":
            show_work_project(arguments.database, arguments.project)
        elif arguments.command == "project-add":
            add_work_project_to_conversation(
                arguments.database,
                arguments.conversation,
                arguments.project,
            )
        elif arguments.command == "project-remove":
            remove_work_project_from_conversation(
                arguments.database,
                arguments.conversation,
                arguments.project,
            )
        elif arguments.command == "project-rename":
            rename_work_project(
                arguments.database,
                arguments.project,
                arguments.new_name,
            )
        elif arguments.command == "categories":
            list_categories(arguments.database)
        elif arguments.command == "category-add":
            add_category_to_conversation(
                arguments.database,
                arguments.conversation,
                arguments.category,
            )
        elif arguments.command == "category-remove":
            remove_category_from_conversation(
                arguments.database,
                arguments.conversation,
                arguments.category,
            )
        elif arguments.command == "category-add-search":
            bulk_add_category_from_search(
                arguments.database,
                arguments.category,
                arguments.query,
                title_only=arguments.title_only,
                min_occurrences=arguments.min_occurrences,
                min_messages=arguments.min_messages,
                apply=arguments.apply,
                limit=arguments.limit,
            )
        elif arguments.command == "category-suggest":
            print_classification_suggestions(
                arguments.database,
                arguments.query,
                title_only=arguments.title_only,
                min_occurrences=arguments.min_occurrences,
                min_messages=arguments.min_messages,
                limit=arguments.limit,
            )
        elif arguments.command == "category-clear":
            clear_category_assignments(
                arguments.database,
                arguments.category,
                apply=arguments.apply,
                limit=arguments.limit,
            )
        elif arguments.command == "tags":
            list_tags(arguments.database)
        elif arguments.command == "tag-add":
            add_tag_to_conversation(
                arguments.database,
                arguments.conversation,
                arguments.tag,
            )
        elif arguments.command == "tag-remove":
            remove_tag_from_conversation(
                arguments.database,
                arguments.conversation,
                arguments.tag,
            )
        elif arguments.command == "tag-add-search":
            bulk_add_tag_from_search(
                arguments.database,
                arguments.tag,
                arguments.query,
                title_only=arguments.title_only,
                min_occurrences=arguments.min_occurrences,
                min_messages=arguments.min_messages,
                apply=arguments.apply,
                limit=arguments.limit,
            )
        elif arguments.command == "tag-suggest":
            print_classification_suggestions(
                arguments.database,
                arguments.query,
                title_only=arguments.title_only,
                min_occurrences=arguments.min_occurrences,
                min_messages=arguments.min_messages,
                limit=arguments.limit,
            )
        elif arguments.command == "tag-clear":
            clear_tag_assignments(
                arguments.database,
                arguments.tag,
                apply=arguments.apply,
                limit=arguments.limit,
            )
        else:
            parser.error(f"Unknown command: {arguments.command}")

    except (sqlite3.Error, OSError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
