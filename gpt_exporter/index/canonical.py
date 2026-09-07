"""Index provider-neutral canonical conversations into the existing archive DB."""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from gpt_exporter.core import CanonicalConversation


CANONICAL_SOURCE_SCHEMA = "gpt-exporter-canonical-index-source-v1"


@lru_cache(maxsize=1)
def _database_helpers() -> ModuleType:
    """Load transitional SQLite helpers lazily without import diagnostics."""
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        from . import _legacy_indexer
    return _legacy_indexer


def ensure_canonical_source_schema(connection: sqlite3.Connection) -> None:
    """Add provider-neutral provenance without disturbing the v4 query schema."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_conversation_sources (
            conversation_id TEXT PRIMARY KEY
                REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            schema_version TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS canonical_sources_provider_idx "
        "ON canonical_conversation_sources(provider_id)"
    )


def index_canonical_conversation(
    connection: sqlite3.Connection,
    conversation: CanonicalConversation,
    *,
    source_path: Path,
    archive_root: Path,
    force: bool = False,
) -> bool:
    """Insert/update one canonical conversation and all searchable messages."""
    del archive_root  # Canonical indexing intentionally has no DOCX lookup dependency.
    db = _database_helpers()
    source_path = Path(source_path).resolve()
    source_mtime_ns = source_path.stat().st_mtime_ns
    ensure_canonical_source_schema(connection)

    existing = connection.execute(
        "SELECT source_mtime_ns FROM canonical_conversation_sources WHERE conversation_id = ?",
        (conversation.conversation_id,),
    ).fetchone()
    if not force and existing and existing["source_mtime_ns"] == source_mtime_ns:
        return False

    indexed_at = db.now_iso()
    title = conversation.title.strip() or "Untitled conversation"

    with connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, created_at, updated_at,
                source_json_path, source_mtime_ns, docx_path, indexed_at,
                primary_origin_type, primary_origin_id,
                gizmo_id, gizmo_type, conversation_template_id,
                conversation_origin, default_model_slug
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'standard', NULL, NULL, NULL, NULL, NULL, NULL)
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
                conversation.conversation_id,
                title,
                conversation.created_at,
                conversation.updated_at,
                str(source_path),
                source_mtime_ns,
                indexed_at,
            ),
        )

        db.delete_message_index_rows(connection, conversation.conversation_id)

        for position, message in enumerate(conversation.messages, start=1):
            body = message.content.strip()
            if not body:
                continue
            message_id = message.message_id or f"message-{position}"
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_id, message_order,
                    author_role, created_at, content_type, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    message_id,
                    position,
                    message.role or "unknown",
                    message.created_at,
                    "canonical_text",
                    body,
                ),
            )
            connection.execute(
                """
                INSERT INTO messages_fts (
                    rowid, body, title, conversation_id, message_id, author_role
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cursor.lastrowid,
                    body,
                    title,
                    conversation.conversation_id,
                    message_id,
                    message.role or "unknown",
                ),
            )

        for category_name in conversation.category_hints:
            category = db.get_or_create_category(connection, category_name)
            connection.execute(
                """
                INSERT OR IGNORE INTO conversation_categories (
                    conversation_id, category_id, assigned_at
                ) VALUES (?, ?, ?)
                """,
                (conversation.conversation_id, category["category_id"], indexed_at),
            )

        connection.execute(
            """
            INSERT INTO canonical_conversation_sources (
                conversation_id, provider_id, source_path, source_mtime_ns,
                metadata_json, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                provider_id = excluded.provider_id,
                source_path = excluded.source_path,
                source_mtime_ns = excluded.source_mtime_ns,
                metadata_json = excluded.metadata_json,
                schema_version = excluded.schema_version
            """,
            (
                conversation.conversation_id,
                conversation.provider_id,
                str(source_path),
                source_mtime_ns,
                json.dumps(dict(conversation.metadata), ensure_ascii=False, sort_keys=True),
                CANONICAL_SOURCE_SCHEMA,
            ),
        )

    return True
