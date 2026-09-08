"""Shared SQLite access layer for the ChatGPT archive browser.

This module intentionally depends only on the Python standard library and on the
SQLite schema created by index_chatgpt_archive07.py (schema version 4).
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 4
WHITESPACE_RE = re.compile(r"\s+")
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9+._-]{2,}")

# Deliberately conservative title-keyword stop list.  It is not intended to be
# linguistic analysis; it merely keeps the visual cloud useful.
STOP_WORDS = {
    "avec", "avoir", "dans", "des", "du", "elle", "elles", "est", "et", "être",
    "les", "leur", "mais", "nous", "pour", "que", "qui", "sur", "une", "vous",
    "aux", "ces", "cette", "comme", "comment", "de", "en", "la", "le", "un",
    "the", "and", "for", "from", "into", "of", "on", "or", "the", "to", "with",
    "analyse", "aide", "choix", "comparaison", "configuration", "finalisation",
    "gestion", "mise", "nouveautés", "probleme", "problème", "projet", "reprise",
    "salut", "suivi", "test", "tests", "version",
}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return WHITESPACE_RE.sub(" ", str(value)).strip()


def search_terms(user_query: str) -> list[str]:
    """Return unique literal whitespace-delimited search terms."""
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in user_query.split():
        term = raw_term.strip().strip('"')
        folded = term.casefold()
        if term and folded not in seen:
            seen.add(folded)
            terms.append(term)
    return terms


@dataclass(frozen=True)
class SearchToken:
    """One token in the lightweight Everything-inspired search syntax."""

    kind: str
    value: str = ""


SearchNode = tuple[Any, ...]


def tokenize_search_query(user_query: str) -> list[SearchToken]:
    """Tokenize the small GUI search language.

    Syntax intentionally mirrors the useful subset of Voidtools Everything:

    - whitespace: implicit AND
    - ``!``: NOT
    - ``|``: OR
    - ``<`` and ``>``: grouping
    - ``"..."``: exact FTS phrase
    - plain terms: FTS prefix terms

    The tokenizer is deliberately lenient because the GUI searches while the
    user is typing.  An unmatched quote simply consumes the rest of the input.
    """
    tokens: list[SearchToken] = []
    index = 0
    length = len(user_query)

    while index < length:
        char = user_query[index]
        if char.isspace():
            index += 1
            continue
        if char == "!":
            tokens.append(SearchToken("NOT"))
            index += 1
            continue
        if char == "|":
            tokens.append(SearchToken("OR"))
            index += 1
            continue
        if char == "<":
            tokens.append(SearchToken("LPAREN"))
            index += 1
            continue
        if char == ">":
            tokens.append(SearchToken("RPAREN"))
            index += 1
            continue
        if char == '"':
            index += 1
            start = index
            while index < length and user_query[index] != '"':
                index += 1
            value = normalize_text(user_query[start:index])
            if value:
                tokens.append(SearchToken("PHRASE", value))
            if index < length and user_query[index] == '"':
                index += 1
            continue

        start = index
        while (
            index < length
            and not user_query[index].isspace()
            and user_query[index] not in '!|<>"'
        ):
            index += 1
        value = user_query[start:index].strip()
        if value:
            tokens.append(SearchToken("TERM", value))

    return tokens


class _SearchParser:
    """Lenient recursive-descent parser for the GUI search syntax."""

    def __init__(self, tokens: Sequence[SearchToken]) -> None:
        self.tokens = list(tokens)
        self.position = 0

    def _peek(self) -> SearchToken | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def _take(self) -> SearchToken | None:
        token = self._peek()
        if token is not None:
            self.position += 1
        return token

    def parse(self) -> SearchNode | None:
        # Ignore accidental leading OR / closing-group tokens while typing.
        while self._peek() and self._peek().kind in {"OR", "RPAREN"}:
            self._take()
        return self._parse_or()

    def _parse_or(self) -> SearchNode | None:
        left = self._parse_and()
        while self._peek() and self._peek().kind == "OR":
            self._take()
            right = self._parse_and()
            # A trailing ``|`` is common while typing.  Keep the left side.
            if right is None:
                break
            if left is None:
                left = right
            else:
                left = ("OR", left, right)
        return left

    def _parse_and(self) -> SearchNode | None:
        left = self._parse_unary()
        while True:
            token = self._peek()
            if token is None or token.kind in {"OR", "RPAREN"}:
                break
            right = self._parse_unary()
            if right is None:
                # Consume junk/incomplete operators so the live search cannot
                # get stuck in a loop.
                if self._peek() is token:
                    self._take()
                continue
            if left is None:
                left = right
            else:
                left = ("AND", left, right)
        return left

    def _parse_unary(self) -> SearchNode | None:
        negate = False
        while self._peek() and self._peek().kind == "NOT":
            self._take()
            negate = not negate

        token = self._peek()
        if token is None:
            return None

        node: SearchNode | None
        if token.kind == "LPAREN":
            self._take()
            node = self._parse_or()
            if self._peek() and self._peek().kind == "RPAREN":
                self._take()
        elif token.kind in {"TERM", "PHRASE"}:
            self._take()
            node = ("ATOM", token.value, token.kind == "PHRASE")
        elif token.kind == "RPAREN":
            return None
        else:
            self._take()
            return None

        if node is not None and negate:
            node = ("NOT", node)
        return node


def parse_search_query(user_query: str) -> SearchNode | None:
    """Parse a user query into a conversation-level boolean expression."""
    return _SearchParser(tokenize_search_query(user_query)).parse()


def _fts_quote(value: str) -> str:
    return value.replace('"', '""')


def _fts_atom_query(value: str, *, phrase: bool, columns: Sequence[str]) -> str:
    """Build one safe FTS5 atom for the requested columns."""
    quoted = f'"{_fts_quote(value)}"'
    expression = quoted if phrase else f"{quoted}*"
    return " OR ".join(f"{column} : {expression}" for column in columns)


def _atom_conversation_ids(
    connection: sqlite3.Connection,
    value: str,
    *,
    phrase: bool,
) -> set[str]:
    fts_query = f"({_fts_atom_query(value, phrase=phrase, columns=('body', 'title'))})"
    return {
        row["conversation_id"]
        for row in connection.execute(
            "SELECT DISTINCT conversation_id FROM messages_fts WHERE messages_fts MATCH ?",
            (fts_query,),
        )
    }


def _evaluate_search_node(
    connection: sqlite3.Connection,
    node: SearchNode,
    universe: set[str],
    atom_cache: dict[tuple[str, bool], set[str]],
) -> set[str]:
    kind = node[0]
    if kind == "ATOM":
        key = (str(node[1]), bool(node[2]))
        if key not in atom_cache:
            atom_cache[key] = _atom_conversation_ids(
                connection,
                key[0],
                phrase=key[1],
            )
        return set(atom_cache[key])
    if kind == "NOT":
        return universe - _evaluate_search_node(connection, node[1], universe, atom_cache)
    if kind == "AND":
        return _evaluate_search_node(connection, node[1], universe, atom_cache) & _evaluate_search_node(
            connection, node[2], universe, atom_cache
        )
    if kind == "OR":
        return _evaluate_search_node(connection, node[1], universe, atom_cache) | _evaluate_search_node(
            connection, node[2], universe, atom_cache
        )
    raise ValueError(f"Unknown search node: {kind}")


def _positive_search_atoms(node: SearchNode | None, *, negated: bool = False) -> list[tuple[str, bool]]:
    """Return positive atoms for the message-preview query."""
    if node is None:
        return []
    kind = node[0]
    if kind == "ATOM":
        return [] if negated else [(str(node[1]), bool(node[2]))]
    if kind == "NOT":
        return _positive_search_atoms(node[1], negated=not negated)
    if kind in {"AND", "OR"}:
        return _positive_search_atoms(node[1], negated=negated) + _positive_search_atoms(
            node[2], negated=negated
        )
    return []


def make_body_preview_fts_query(user_query: str) -> str | None:
    """Build a broad body-only FTS query for the details preview.

    Conversation filtering uses the full boolean expression.  The preview only
    needs to surface useful matching messages, so positive atoms are OR'ed and
    negative-only queries fall back to the first messages of the conversation.
    """
    node = parse_search_query(user_query)
    atoms = _positive_search_atoms(node)
    unique: list[tuple[str, bool]] = []
    seen: set[tuple[str, bool]] = set()
    for atom in atoms:
        key = (atom[0].casefold(), atom[1])
        if key not in seen:
            seen.add(key)
            unique.append(atom)
    if not unique:
        return None
    return " OR ".join(
        f"({_fts_atom_query(value, phrase=phrase, columns=('body',))})"
        for value, phrase in unique
    )


def connect_database(database_path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    """Open and validate a schema-v4 archive database."""
    database_path = Path(database_path)
    if readonly:
        if not database_path.is_file():
            raise FileNotFoundError(f"Database does not exist: {database_path}")
        connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    conversations_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    if not conversations_table:
        connection.close()
        raise ValueError(
            "The selected SQLite file is not a ChatGPT archive index. "
            "Run index_chatgpt_archive07.py first."
        )

    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version < SCHEMA_VERSION:
        connection.close()
        raise ValueError(
            f"Database schema version is {version}; version {SCHEMA_VERSION} or newer is required. "
            "Run index_chatgpt_archive07.py once to migrate it."
        )
    return connection


def _origin_display(row: sqlite3.Row) -> str:
    origin_type = row["primary_origin_type"] or "standard"
    origin_id = row["primary_origin_id"]
    if origin_id:
        label = row["origin_label"] or origin_id
        return f"{origin_type}: {label}"
    return origin_type


def list_projects(database_path: Path) -> list[dict[str, Any]]:
    with connect_database(database_path, readonly=True) as connection:
        rows = connection.execute(
            """
            SELECT
                wp.project_id,
                wp.name,
                wp.description,
                COUNT(cwp.conversation_id) AS conversation_count
            FROM work_projects AS wp
            LEFT JOIN conversation_work_projects AS cwp
                ON cwp.project_id = wp.project_id
            GROUP BY wp.project_id
            ORDER BY wp.name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_origins(database_path: Path) -> list[str]:
    with connect_database(database_path, readonly=True) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT
                c.primary_origin_type,
                c.primary_origin_id,
                o.label AS origin_label
            FROM conversations AS c
            LEFT JOIN origins AS o ON o.origin_id = c.primary_origin_id
            ORDER BY c.primary_origin_type, COALESCE(o.label, c.primary_origin_id, '') COLLATE NOCASE
            """
        ).fetchall()
    values = []
    for row in rows:
        values.append(_origin_display(row))
    return values


def list_tags(database_path: Path) -> list[str]:
    with connect_database(database_path, readonly=True) as connection:
        return [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM tags ORDER BY name COLLATE NOCASE"
            ).fetchall()
        ]


def list_categories(database_path: Path) -> list[str]:
    with connect_database(database_path, readonly=True) as connection:
        return [
            row["name"]
            for row in connection.execute(
                "SELECT name FROM categories ORDER BY name COLLATE NOCASE"
            ).fetchall()
        ]


def _matching_conversation_ids(connection: sqlite3.Connection, query: str) -> set[str] | None:
    query = normalize_text(query)
    if not query:
        return None
    node = parse_search_query(query)
    if node is None:
        return None

    universe = {
        row["conversation_id"]
        for row in connection.execute("SELECT conversation_id FROM conversations")
    }
    return _evaluate_search_node(connection, node, universe, {})


def query_conversations(
    database_path: Path,
    *,
    search: str = "",
    origin: str = "",
    project: str = "",
    tag: str = "",
    category: str = "",
    unprojected: bool = False,
    multiple_projects: bool = False,
    recursive_project: bool = False,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Return GUI-ready conversation rows using combined filters."""
    with connect_database(database_path, readonly=True) as connection:
        conditions: list[str] = []
        parameters: list[Any] = []

        matched_ids = _matching_conversation_ids(connection, search)
        if matched_ids is not None:
            if not matched_ids:
                return []
            placeholders = ",".join("?" for _ in matched_ids)
            conditions.append(f"c.conversation_id IN ({placeholders})")
            parameters.extend(sorted(matched_ids))

        if origin:
            # The displayed form is either "standard" or "type: label".
            if origin == "standard":
                conditions.append("c.primary_origin_type = 'standard'")
            elif ": " in origin:
                origin_type, label_or_id = origin.split(": ", 1)
                conditions.append("c.primary_origin_type = ?")
                parameters.append(origin_type)
                conditions.append("COALESCE(o.label, c.primary_origin_id) = ? COLLATE NOCASE")
                parameters.append(label_or_id)
            else:
                conditions.append("c.primary_origin_type = ?")
                parameters.append(origin)

        if project:
            # Resolve semantic project paths in Python so cosmetic whitespace
            # around slash separators never changes direct/recursive matching.
            wanted = normalize_project_path(project)
            project_rows = connection.execute(
                "SELECT project_id, name FROM work_projects ORDER BY project_id"
            ).fetchall()
            if recursive_project:
                project_ids = [
                    int(row["project_id"])
                    for row in project_rows
                    if _project_path_startswith(row["name"], wanted)
                ]
            else:
                wanted_key = wanted.casefold()
                project_ids = [
                    int(row["project_id"])
                    for row in project_rows
                    if normalize_project_path(row["name"]).casefold() == wanted_key
                ]

            if not project_ids:
                return []
            placeholders = ",".join("?" for _ in project_ids)
            conditions.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM conversation_work_projects AS cwp2
                    WHERE cwp2.conversation_id = c.conversation_id
                      AND cwp2.project_id IN ({placeholders})
                )
                """
            )
            parameters.extend(project_ids)

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

        if multiple_projects:
            conditions.append(
                """
                (
                    SELECT COUNT(DISTINCT cwp4.project_id)
                    FROM conversation_work_projects AS cwp4
                    WHERE cwp4.conversation_id = c.conversation_id
                ) >= 2
                """
            )

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""
        parameters.append(limit)

        rows = connection.execute(
            f"""
            SELECT
                c.conversation_id,
                c.title,
                c.created_at,
                c.updated_at,
                c.primary_origin_type,
                c.primary_origin_id,
                o.label AS origin_label,
                c.docx_path,
                c.source_json_path,
                COUNT(DISTINCT m.id) AS message_count,
                GROUP_CONCAT(DISTINCT wp.name) AS projects,
                GROUP_CONCAT(DISTINCT cat.name) AS categories,
                GROUP_CONCAT(DISTINCT t.name) AS tags
            FROM conversations AS c
            LEFT JOIN origins AS o ON o.origin_id = c.primary_origin_id
            LEFT JOIN messages AS m ON m.conversation_id = c.conversation_id
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
            ORDER BY c.created_at DESC, c.title COLLATE NOCASE
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["origin_display"] = _origin_display(row)
        item["date_display"] = (row["created_at"] or "")[:10]
        item["projects_display"] = row["projects"] or ""
        item["categories_display"] = row["categories"] or ""
        item["tags_display"] = row["tags"] or ""
        result.append(item)
    return result


def get_conversation(database_path: Path, conversation_id: str) -> dict[str, Any] | None:
    with connect_database(database_path, readonly=True) as connection:
        row = connection.execute(
            """
            SELECT c.*, o.label AS origin_label
            FROM conversations AS c
            LEFT JOIN origins AS o ON o.origin_id = c.primary_origin_id
            WHERE c.conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if not row:
            return None

        result = dict(row)
        result["origin_display"] = _origin_display(row)
        result["projects"] = [
            r["name"]
            for r in connection.execute(
                """
                SELECT wp.name
                FROM conversation_work_projects AS cwp
                JOIN work_projects AS wp ON wp.project_id = cwp.project_id
                WHERE cwp.conversation_id = ?
                ORDER BY wp.name COLLATE NOCASE
                """,
                (conversation_id,),
            ).fetchall()
        ]
        result["categories"] = [
            r["name"]
            for r in connection.execute(
                """
                SELECT cat.name
                FROM conversation_categories AS cc
                JOIN categories AS cat ON cat.category_id = cc.category_id
                WHERE cc.conversation_id = ?
                ORDER BY cat.name COLLATE NOCASE
                """,
                (conversation_id,),
            ).fetchall()
        ]
        result["tags"] = [
            r["name"]
            for r in connection.execute(
                """
                SELECT t.name
                FROM conversation_tags AS ct
                JOIN tags AS t ON t.tag_id = ct.tag_id
                WHERE ct.conversation_id = ?
                ORDER BY t.name COLLATE NOCASE
                """,
                (conversation_id,),
            ).fetchall()
        ]
        result["message_count"] = connection.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()["n"]
        return result


def matching_message_excerpts(
    database_path: Path,
    conversation_id: str,
    query: str,
    *,
    limit: int = 8,
    excerpt_chars: int = 700,
) -> list[dict[str, Any]]:
    """Return relevant message excerpts for the details pane."""
    query = normalize_text(query)
    with connect_database(database_path, readonly=True) as connection:
        preview_fts_query = make_body_preview_fts_query(query) if query else None
        if preview_fts_query:
            rows = connection.execute(
                """
                SELECT
                    m.message_order,
                    m.author_role,
                    m.created_at,
                    m.body,
                    bm25(messages_fts) AS rank
                FROM messages_fts
                JOIN messages AS m ON m.id = messages_fts.rowid
                WHERE messages_fts MATCH ?
                  AND m.conversation_id = ?
                ORDER BY rank
                LIMIT ?
                """,
                (preview_fts_query, conversation_id, limit),
            ).fetchall()
            # A conversation may match through its title only.  In that case,
            # still show useful context instead of an empty preview pane.
            if not rows:
                rows = connection.execute(
                    """
                    SELECT message_order, author_role, created_at, body, 0.0 AS rank
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY message_order
                    LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT message_order, author_role, created_at, body, 0.0 AS rank
                FROM messages
                WHERE conversation_id = ?
                ORDER BY message_order
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()

    result = []
    for row in rows:
        body = row["body"]
        if len(body) > excerpt_chars:
            body = body[:excerpt_chars].rstrip() + "…"
        result.append(
            {
                "message_order": row["message_order"],
                "author_role": row["author_role"],
                "created_at": row["created_at"],
                "body": body,
            }
        )
    return result


def project_path_parts(value: str) -> tuple[str, ...]:
    """Return normalized slash-separated project path components."""
    parts: list[str] = []
    for raw_part in str(value or "").split("/"):
        part = normalize_text(raw_part)
        if part:
            parts.append(part)
    return tuple(parts)


def normalize_project_path(value: str) -> str:
    """Normalize a project path while keeping it human-readable in SQLite."""
    return " / ".join(project_path_parts(value))


def join_project_path(parent: str, child: str) -> str:
    """Join a visual branch path and one child segment."""
    child_parts = project_path_parts(child)
    if len(child_parts) != 1:
        raise ValueError("Sub-project name must contain exactly one path segment.")
    parent_parts = project_path_parts(parent)
    return " / ".join((*parent_parts, child_parts[0]))


def _project_path_startswith(name: str, prefix: str) -> bool:
    name_parts = project_path_parts(name)
    prefix_parts = project_path_parts(prefix)
    if not prefix_parts or len(name_parts) < len(prefix_parts):
        return False
    return tuple(part.casefold() for part in name_parts[: len(prefix_parts)]) == tuple(
        part.casefold() for part in prefix_parts
    )


def project_branch_stats(database_path: Path, branch_path: str) -> dict[str, int]:
    """Count concrete projects and assignments inside a visual branch."""
    branch = normalize_project_path(branch_path)
    if not branch:
        raise ValueError("Project branch cannot be empty.")
    with connect_database(database_path, readonly=True) as connection:
        rows = connection.execute(
            "SELECT project_id, name FROM work_projects ORDER BY project_id"
        ).fetchall()
        project_ids = [
            int(row["project_id"]) for row in rows if _project_path_startswith(row["name"], branch)
        ]
        if not project_ids:
            return {"project_count": 0, "assignment_count": 0}
        placeholders = ",".join("?" for _ in project_ids)
        assignment_count = connection.execute(
            f"SELECT COUNT(*) AS n FROM conversation_work_projects "
            f"WHERE project_id IN ({placeholders})",
            project_ids,
        ).fetchone()["n"]
    return {
        "project_count": len(project_ids),
        "assignment_count": int(assignment_count),
    }


def rename_project_branch(database_path: Path, old_branch: str, new_branch: str) -> int:
    """Rename a visual project branch and every concrete descendant project."""
    old_normalized = normalize_project_path(old_branch)
    new_normalized = normalize_project_path(new_branch)
    if not old_normalized or not new_normalized:
        raise ValueError("Project branch names cannot be empty.")

    old_parts = project_path_parts(old_normalized)
    new_parts = project_path_parts(new_normalized)

    with connect_database(database_path) as connection:
        rows = connection.execute(
            "SELECT project_id, name FROM work_projects ORDER BY project_id"
        ).fetchall()
        selected = [row for row in rows if _project_path_startswith(row["name"], old_normalized)]
        if not selected:
            raise ValueError(f"Project branch not found: {old_normalized}")

        selected_ids = {int(row["project_id"]) for row in selected}
        unaffected_rows = [
            row for row in rows if int(row["project_id"]) not in selected_ids
        ]
        unaffected_paths = {
            normalize_project_path(row["name"]).casefold() for row in unaffected_rows
        }

        # Do not silently merge two visual branches.  A branch may be synthetic
        # (there is no exact work_projects row for it), so check descendants too.
        for row in unaffected_rows:
            if _project_path_startswith(row["name"], new_normalized):
                raise ValueError(
                    f"Cannot rename branch: '{new_normalized}' already exists."
                )

        targets: list[tuple[int, str]] = []
        target_keys: set[str] = set()
        for row in selected:
            original_parts = project_path_parts(row["name"])
            suffix = original_parts[len(old_parts) :]
            target = " / ".join((*new_parts, *suffix))
            key = target.casefold()
            if key in unaffected_paths:
                raise ValueError(f"Cannot rename branch: project '{target}' already exists.")
            if key in target_keys:
                raise ValueError(f"Cannot rename branch: duplicate target '{target}'.")
            target_keys.add(key)
            targets.append((int(row["project_id"]), target))

        # Avoid UNIQUE-name conflicts while paths are being rewritten.
        token = uuid.uuid4().hex
        for project_id, _target in targets:
            connection.execute(
                "UPDATE work_projects SET name = ? WHERE project_id = ?",
                (f"__rename_tmp__{token}__{project_id}", project_id),
            )
        for project_id, target in targets:
            connection.execute(
                "UPDATE work_projects SET name = ? WHERE project_id = ?",
                (target, project_id),
            )
        connection.commit()
        return len(targets)


def project_move_destination_path(branch_path: str, new_parent_path: str) -> str:
    """Return the semantic destination path for moving one visual branch.

    ``new_parent_path`` may be empty, which means the synthetic ``Projects``
    root.  Moving a branch onto itself, into one of its descendants, or back
    onto its current parent is rejected before any database change occurs.
    """
    branch = normalize_project_path(branch_path)
    parent = normalize_project_path(new_parent_path)
    if not branch:
        raise ValueError("Project branch cannot be empty.")

    branch_parts = project_path_parts(branch)
    parent_parts = project_path_parts(parent)
    folded_branch = tuple(part.casefold() for part in branch_parts)
    folded_parent = tuple(part.casefold() for part in parent_parts)

    if folded_parent[: len(folded_branch)] == folded_branch:
        raise ValueError("A branch cannot be moved onto itself or into one of its descendants.")

    destination = " / ".join((*parent_parts, branch_parts[-1]))
    if destination.casefold() == branch.casefold():
        raise ValueError("This branch is already under that parent.")
    return destination


def rebase_project_path(value: str, old_prefix: str, new_prefix: str) -> str:
    """Rewrite ``value`` when it lives inside a moved/renamed branch."""
    normalized = normalize_project_path(value)
    old_normalized = normalize_project_path(old_prefix)
    new_normalized = normalize_project_path(new_prefix)
    if not normalized or not old_normalized or not new_normalized:
        return normalized
    if not _project_path_startswith(normalized, old_normalized):
        return normalized

    value_parts = project_path_parts(normalized)
    old_parts = project_path_parts(old_normalized)
    new_parts = project_path_parts(new_normalized)
    suffix = value_parts[len(old_parts) :]
    return " / ".join((*new_parts, *suffix))


def move_project_branch(
    database_path: Path, branch_path: str, new_parent_path: str
) -> dict[str, Any]:
    """Move a visual project branch below another branch (or Projects root)."""
    old_path = normalize_project_path(branch_path)
    new_path = project_move_destination_path(old_path, new_parent_path)
    project_count = rename_project_branch(database_path, old_path, new_path)
    return {
        "old_path": old_path,
        "new_path": new_path,
        "project_count": project_count,
    }


def delete_project_branch(database_path: Path, branch_path: str) -> dict[str, int]:
    """Delete all concrete projects in a visual branch and their assignments."""
    branch = normalize_project_path(branch_path)
    if not branch:
        raise ValueError("Project branch cannot be empty.")

    with connect_database(database_path) as connection:
        rows = connection.execute(
            "SELECT project_id, name FROM work_projects ORDER BY project_id"
        ).fetchall()
        project_ids = [
            int(row["project_id"]) for row in rows if _project_path_startswith(row["name"], branch)
        ]
        if not project_ids:
            return {"project_count": 0, "assignment_count": 0}

        placeholders = ",".join("?" for _ in project_ids)
        assignment_count = connection.execute(
            f"SELECT COUNT(*) AS n FROM conversation_work_projects "
            f"WHERE project_id IN ({placeholders})",
            project_ids,
        ).fetchone()["n"]
        connection.execute(
            f"DELETE FROM conversation_work_projects WHERE project_id IN ({placeholders})",
            project_ids,
        )
        connection.execute(
            f"DELETE FROM work_projects WHERE project_id IN ({placeholders})",
            project_ids,
        )
        connection.commit()
        return {
            "project_count": len(project_ids),
            "assignment_count": int(assignment_count),
        }


def _find_project_by_semantic_path(
    connection: sqlite3.Connection, name: str
) -> sqlite3.Row | None:
    """Find a project ignoring cosmetic whitespace around slash separators."""
    wanted = normalize_project_path(name).casefold()
    if not wanted:
        return None
    rows = connection.execute(
        "SELECT project_id, name FROM work_projects ORDER BY project_id"
    ).fetchall()
    for row in rows:
        if normalize_project_path(row["name"]).casefold() == wanted:
            return row
    return None


def get_or_create_project(connection: sqlite3.Connection, name: str) -> sqlite3.Row:
    clean = normalize_project_path(name)
    if not clean:
        raise ValueError("Project name cannot be empty.")
    row = _find_project_by_semantic_path(connection, clean)
    if row:
        return row
    cursor = connection.execute(
        "INSERT INTO work_projects (name, description, created_at) VALUES (?, NULL, datetime('now'))",
        (clean,),
    )
    return connection.execute(
        "SELECT project_id, name FROM work_projects WHERE project_id = ?",
        (cursor.lastrowid,),
    ).fetchone()


def assign_project(database_path: Path, conversation_id: str, project_name: str) -> bool:
    """Assign a project; return True only when a new link was written."""
    with connect_database(database_path) as connection:
        project = get_or_create_project(connection, project_name)
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO conversation_work_projects (
                conversation_id, project_id, assigned_at
            ) VALUES (?, ?, datetime('now'))
            """,
            (conversation_id, project["project_id"]),
        )
        connection.commit()
        return cursor.rowcount > 0


def remove_project(database_path: Path, conversation_id: str, project_name: str) -> bool:
    with connect_database(database_path) as connection:
        cursor = connection.execute(
            """
            DELETE FROM conversation_work_projects
            WHERE conversation_id = ?
              AND project_id = (
                  SELECT project_id FROM work_projects WHERE name = ? COLLATE NOCASE
              )
            """,
            (conversation_id, project_name),
        )
        connection.commit()
        return cursor.rowcount > 0


def create_project(database_path: Path, project_name: str) -> str:
    with connect_database(database_path) as connection:
        project = get_or_create_project(connection, project_name)
        connection.commit()
        return project["name"]


def rename_project(database_path: Path, old_name: str, new_name: str) -> None:
    clean = normalize_project_path(new_name)
    if not clean:
        raise ValueError("Project name cannot be empty.")
    with connect_database(database_path) as connection:
        existing = connection.execute(
            "SELECT project_id FROM work_projects WHERE name = ? COLLATE NOCASE",
            (clean,),
        ).fetchone()
        source = connection.execute(
            "SELECT project_id FROM work_projects WHERE name = ? COLLATE NOCASE",
            (old_name,),
        ).fetchone()
        if not source:
            raise ValueError(f"Project not found: {old_name}")
        if existing and existing["project_id"] != source["project_id"]:
            raise ValueError(f"A project named '{clean}' already exists.")
        connection.execute(
            "UPDATE work_projects SET name = ? WHERE project_id = ?",
            (clean, source["project_id"]),
        )
        connection.commit()


def delete_project(database_path: Path, project_name: str) -> int:
    """Delete a work project and its assignments; return number of assignments removed."""
    with connect_database(database_path) as connection:
        project = connection.execute(
            "SELECT project_id FROM work_projects WHERE name = ? COLLATE NOCASE",
            (project_name,),
        ).fetchone()
        if not project:
            return 0
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM conversation_work_projects WHERE project_id = ?",
            (project["project_id"],),
        ).fetchone()["n"]
        connection.execute("DELETE FROM work_projects WHERE project_id = ?", (project["project_id"],))
        connection.commit()
        return count


def keyword_counts(rows: Sequence[dict[str, Any]], *, limit: int = 45) -> list[tuple[str, int]]:
    """Build a lightweight keyword cloud from current result titles and manual tags."""
    counts: Counter[str] = Counter()
    canonical: dict[str, str] = {}

    for row in rows:
        for token in WORD_RE.findall(row.get("title", "")):
            folded = token.casefold().strip("._-")
            if len(folded) < 3 or folded in STOP_WORDS or folded.isdigit():
                continue
            canonical.setdefault(folded, token)
            counts[folded] += 1

        tags = row.get("tags_display") or ""
        for tag in filter(None, (part.strip() for part in tags.split(","))):
            folded = tag.casefold()
            canonical.setdefault(folded, tag)
            # Manual tags deserve slightly more visual weight than a title token.
            counts[folded] += 2

    return [(canonical[key], count) for key, count in counts.most_common(limit)]
