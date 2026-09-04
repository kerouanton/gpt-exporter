"""Import normalized legacy DOCX turns into the existing searchable SQLite index."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from gpt_exporter.index._legacy_indexer import (
    connect_database,
    delete_message_index_rows,
    now_iso,
)


LEGACY_SQLITE_IMPORT_VERSION = "legacy-sqlite-import-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def legacy_conversation_id(source_sha256: str) -> str:
    """Return a stable conversation ID derived from immutable source bytes."""
    return f"legacy-docx-{source_sha256.lower()}"


def ensure_legacy_provenance_schema(connection: sqlite3.Connection) -> None:
    """Create rebuildable legacy-only provenance without changing schema v4."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS legacy_conversation_sources (
            conversation_id TEXT PRIMARY KEY
                REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            source_type TEXT NOT NULL CHECK(source_type = 'legacy_docx'),
            source_docx_path TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            parser_version TEXT,
            role_inference_version TEXT,
            turn_builder_version TEXT,
            import_version TEXT NOT NULL,
            category_hint TEXT,
            date_hint TEXT,
            starts_mid_conversation INTEGER,
            imported_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS legacy_conversation_sources_sha_idx
            ON legacy_conversation_sources(source_sha256);
        """
    )


def _resolve_source(docx_root: Path, source_filename: str) -> Path:
    direct = docx_root / source_filename
    if direct.is_file():
        return direct.resolve()
    matches = list(docx_root.rglob(source_filename))
    if not matches:
        raise FileNotFoundError(f"Legacy DOCX not found under {docx_root}: {source_filename}")
    if len(matches) > 1:
        raise ValueError(f"Multiple legacy DOCX files match {source_filename}: {matches}")
    return matches[0].resolve()


def _date_hint_iso(date_hint: Any) -> str | None:
    if not isinstance(date_hint, str) or not date_hint.strip():
        return None
    value = date_hint.strip()
    return value + "T00:00:00" if len(value) == 10 else value


def import_legacy_conversation(
    connection: sqlite3.Connection,
    conversation: dict[str, Any],
    *,
    docx_root: Path,
    force: bool = False,
) -> tuple[str, bool, int]:
    source_filename = str(conversation.get("source_filename") or "").strip()
    expected_sha = str(conversation.get("source_sha256") or "").lower().strip()
    if not source_filename or len(expected_sha) != 64:
        raise ValueError("Legacy conversation is missing source filename/SHA-256")

    source = _resolve_source(docx_root, source_filename)
    actual_sha = _sha256(source)
    if actual_sha != expected_sha:
        raise ValueError(
            f"SHA-256 mismatch for {source_filename}: expected {expected_sha}, got {actual_sha}"
        )

    conversation_id = legacy_conversation_id(expected_sha)
    existing = connection.execute(
        "SELECT source_sha256 FROM legacy_conversation_sources WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    if existing and not force and existing["source_sha256"] == expected_sha:
        return conversation_id, False, 0

    title = str(conversation.get("title_hint") or source.stem).strip() or source.stem
    created_at = _date_hint_iso(conversation.get("date_hint"))
    turns = conversation.get("turns")
    if not isinstance(turns, list):
        raise ValueError(f"Invalid normalized turns for {source_filename}")

    indexed_at = now_iso()
    source_mtime_ns = source.stat().st_mtime_ns
    parser_version = str(conversation.get("parser_version") or "").strip() or None
    role_inference_version = conversation.get("role_inference_version")
    turn_builder_version = conversation.get("turn_builder_version")
    starts_mid = conversation.get("starts_mid_conversation")
    starts_mid_db = None if starts_mid is None else int(bool(starts_mid))

    with connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, created_at, updated_at,
                source_json_path, source_mtime_ns, docx_path, indexed_at,
                primary_origin_type, primary_origin_id,
                gizmo_id, gizmo_type, conversation_template_id,
                conversation_origin, default_model_slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'standard', NULL, NULL, NULL, NULL, NULL, NULL)
            ON CONFLICT(conversation_id) DO UPDATE SET
                title = excluded.title,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                source_json_path = excluded.source_json_path,
                source_mtime_ns = excluded.source_mtime_ns,
                docx_path = excluded.docx_path,
                indexed_at = excluded.indexed_at
            """,
            (
                conversation_id,
                title,
                created_at,
                created_at,
                str(source),  # compatibility field; provenance table states the real source type
                source_mtime_ns,
                str(source),
                indexed_at,
            ),
        )

        delete_message_index_rows(connection, conversation_id)

        indexed_turns = 0
        for position, turn in enumerate(turns, start=1):
            if not isinstance(turn, dict):
                continue
            body = str(turn.get("content") or "").strip()
            if not body:
                continue
            role = str(turn.get("role") or "unknown")
            message_id = f"legacy-turn-{position:04d}"
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_id, message_order,
                    author_role, created_at, content_type, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    message_id,
                    position,
                    role,
                    None,
                    "legacy_docx_turn",
                    body,
                ),
            )
            connection.execute(
                """
                INSERT INTO messages_fts (
                    rowid, body, title, conversation_id, message_id, author_role
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (cursor.lastrowid, body, title, conversation_id, message_id, role),
            )
            indexed_turns += 1

        connection.execute(
            """
            INSERT INTO legacy_conversation_sources (
                conversation_id, source_type, source_docx_path, source_filename,
                source_sha256, parser_version, role_inference_version,
                turn_builder_version, import_version, category_hint, date_hint,
                starts_mid_conversation, imported_at
            ) VALUES (?, 'legacy_docx', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                source_docx_path = excluded.source_docx_path,
                source_filename = excluded.source_filename,
                source_sha256 = excluded.source_sha256,
                parser_version = excluded.parser_version,
                role_inference_version = excluded.role_inference_version,
                turn_builder_version = excluded.turn_builder_version,
                import_version = excluded.import_version,
                category_hint = excluded.category_hint,
                date_hint = excluded.date_hint,
                starts_mid_conversation = excluded.starts_mid_conversation,
                imported_at = excluded.imported_at
            """,
            (
                conversation_id,
                str(source),
                source_filename,
                expected_sha,
                parser_version,
                role_inference_version,
                turn_builder_version,
                LEGACY_SQLITE_IMPORT_VERSION,
                conversation.get("category_hint"),
                conversation.get("date_hint"),
                starts_mid_db,
                indexed_at,
            ),
        )

    return conversation_id, True, indexed_turns


def import_legacy_collection(
    payload: dict[str, Any],
    *,
    database_path: Path,
    docx_root: Path,
    force: bool = False,
) -> dict[str, int]:
    conversations = payload.get("conversations")
    if not isinstance(conversations, list):
        raise ValueError("Expected normalized legacy turn collection")

    database_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"updated": 0, "unchanged": 0, "turns": 0, "failed": 0}
    with connect_database(database_path) as connection:
        ensure_legacy_provenance_schema(connection)
        connection.commit()
        for conversation in conversations:
            if not isinstance(conversation, dict):
                counts["failed"] += 1
                continue
            try:
                _, changed, turn_count = import_legacy_conversation(
                    connection,
                    conversation,
                    docx_root=docx_root,
                    force=force,
                )
                if changed:
                    counts["updated"] += 1
                    counts["turns"] += turn_count
                else:
                    counts["unchanged"] += 1
            except (OSError, ValueError, sqlite3.Error):
                counts["failed"] += 1
                raise
    return counts
