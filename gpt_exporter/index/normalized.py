"""Index provider-neutral conversations into the existing archive search schema.

The current v4 browser schema remains compatible. Provider identity is stored in
an additive table so existing project/tag/category metadata and browser queries
remain valid during the incremental migration.
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

from gpt_exporter.model import Conversation

with contextlib.redirect_stdout(io.StringIO()):
    from . import _legacy_indexer as legacy


_LEGACY_INDEX_METADATA_FIELDS = (
    "gizmo_id",
    "gizmo_type",
    "conversation_template_id",
    "conversation_origin",
    "default_model_slug",
)


def _iso(value) -> str | None:
    return value.astimezone().isoformat() if value is not None else None


def _index_metadata_value(conversation: Conversation, key: str) -> str | None:
    value = conversation.index_metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def ensure_provider_schema(connection: sqlite3.Connection) -> None:
    """Add provider provenance without changing the current browser schema version."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_providers (
            conversation_id TEXT PRIMARY KEY
                REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            provider_key TEXT NOT NULL,
            native_conversation_id TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS conversation_providers_key_idx "
        "ON conversation_providers(provider_key)"
    )


def initialize_normalized_database(database_path: Path | str) -> Path:
    """Create the common browser/index schema for a new empty workspace."""

    database = Path(database_path).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = legacy.connect_database(database)
    try:
        ensure_provider_schema(connection)
        connection.commit()
    finally:
        connection.close()
    return database


def index_normalized_conversation(
    connection: sqlite3.Connection,
    conversation: Conversation,
    *,
    source_path: Path | str,
    archive_root: Path | str,
    source_mtime_ns: int = 0,
) -> None:
    """Write one normalized conversation while preserving user organization data."""

    source = Path(source_path).expanduser().resolve()
    archive = Path(archive_root).expanduser().resolve()
    conversation_id = conversation.conversation_id
    title = legacy.normalize_text(conversation.title) or "Untitled conversation"
    docx = legacy.find_docx(archive, conversation_id)
    indexed_at = legacy.now_iso()
    primary = conversation.primary_origin
    primary_origin_type = primary.origin_type if primary is not None else "standard"
    primary_origin_id = primary.origin_id if primary is not None else None
    index_values = {
        key: _index_metadata_value(conversation, key)
        for key in _LEGACY_INDEX_METADATA_FIELDS
    }

    ensure_provider_schema(connection)

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
                _iso(conversation.created_at),
                _iso(conversation.updated_at),
                str(source),
                int(source_mtime_ns),
                str(docx) if docx else None,
                indexed_at,
                primary_origin_type,
                primary_origin_id,
                index_values["gizmo_id"],
                index_values["gizmo_type"],
                index_values["conversation_template_id"],
                index_values["conversation_origin"],
                index_values["default_model_slug"],
            ),
        )

        connection.execute(
            """
            INSERT INTO conversation_providers (
                conversation_id, provider_key, native_conversation_id, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                provider_key = excluded.provider_key,
                native_conversation_id = excluded.native_conversation_id,
                updated_at = excluded.updated_at
            """,
            (
                conversation_id,
                conversation.provider_key,
                conversation.conversation_id,
                indexed_at,
            ),
        )

        legacy.delete_message_index_rows(connection, conversation_id)
        legacy.replace_detected_origins(
            connection,
            conversation_id,
            [
                {
                    "origin_id": origin.origin_id,
                    "origin_type": origin.origin_type,
                    "source": origin.source,
                }
                for origin in conversation.origins
            ],
            primary_origin_id,
        )

        for position, message in enumerate(conversation.indexable_messages, start=1):
            content_type = message.content[0].kind if message.content else None
            body = message.search_text or message.text
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
                    message.message_id,
                    position,
                    message.author_role or "unknown",
                    _iso(message.created_at),
                    content_type,
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
                    conversation_id,
                    message.message_id,
                    message.author_role or "unknown",
                ),
            )


def index_normalized_file(
    provider,
    source_path: Path | str,
    *,
    archive_root: Path | str,
    database_path: Path | str,
) -> Conversation:
    """Normalize one provider-native conversation file and index the result."""

    source = Path(source_path).expanduser().resolve()
    conversation = provider.normalize_conversation(source)
    database = Path(database_path).expanduser().resolve()
    initialize_normalized_database(database)
    connection = legacy.connect_database(database)
    try:
        index_normalized_conversation(
            connection,
            conversation,
            source_path=source,
            archive_root=archive_root,
            source_mtime_ns=source.stat().st_mtime_ns,
        )
    finally:
        connection.close()
    return conversation


__all__ = [
    "ensure_provider_schema",
    "index_normalized_conversation",
    "index_normalized_file",
    "initialize_normalized_database",
]
