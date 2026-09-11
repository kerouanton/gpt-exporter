"""Index provider-neutral canonical conversations into the archive database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable

from gpt_exporter.core import CanonicalConversation
from gpt_exporter.index.storage import (
    delete_message_index_rows,
    get_or_create_category,
    now_iso,
    upsert_provider_metadata,
)

CANONICAL_SOURCE_SCHEMA = "gpt-exporter-canonical-index-source-v1"
ProgressCallback = Callable[[str], None]


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def ensure_canonical_source_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_conversation_sources (
            conversation_id TEXT PRIMARY KEY REFERENCES conversations(conversation_id) ON DELETE CASCADE,
            provider_id TEXT NOT NULL,
            source_path TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            schema_version TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS canonical_sources_provider_idx ON canonical_conversation_sources(provider_id)"
    )


def _origin_from_metadata(conversation: CanonicalConversation) -> tuple[str, str | None]:
    metadata = dict(conversation.metadata)
    origin_type = str(metadata.get("origin_type") or "standard").strip() or "standard"
    origin_id_value = metadata.get("origin_id")
    origin_id = str(origin_id_value).strip() if origin_id_value is not None else None
    return origin_type, (origin_id or None)


def index_canonical_conversation(
    connection: sqlite3.Connection,
    conversation: CanonicalConversation,
    *,
    source_path: Path,
    archive_root: Path,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> bool:
    del archive_root
    source_path = Path(source_path).resolve()
    source_mtime_ns = source_path.stat().st_mtime_ns
    ensure_canonical_source_schema(connection)

    existing = connection.execute(
        "SELECT source_mtime_ns FROM canonical_conversation_sources WHERE conversation_id = ?",
        (conversation.conversation_id,),
    ).fetchone()
    if not force and existing and existing["source_mtime_ns"] == source_mtime_ns:
        return False

    indexed_at = now_iso()
    title = conversation.title.strip() or "Untitled conversation"
    origin_type, origin_id = _origin_from_metadata(conversation)
    total_messages = len(conversation.messages)

    with connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, created_at, updated_at,
                source_json_path, source_mtime_ns, docx_path, indexed_at,
                primary_origin_type, primary_origin_id
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                title = excluded.title,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                source_json_path = excluded.source_json_path,
                source_mtime_ns = excluded.source_mtime_ns,
                docx_path = COALESCE(conversations.docx_path, excluded.docx_path),
                indexed_at = excluded.indexed_at,
                primary_origin_type = excluded.primary_origin_type,
                primary_origin_id = excluded.primary_origin_id
            """,
            (
                conversation.conversation_id,
                title,
                conversation.created_at,
                conversation.updated_at,
                str(source_path),
                source_mtime_ns,
                indexed_at,
                origin_type,
                origin_id,
            ),
        )

        upsert_provider_metadata(
            connection,
            conversation.conversation_id,
            conversation.provider_id,
            conversation.metadata,
        )

        _emit(progress, f"Clearing previous message index rows for {conversation.conversation_id}…")
        delete_message_index_rows(connection, conversation.conversation_id)
        _emit(progress, f"Indexing {total_messages} message(s) for {conversation.conversation_id}…")
        indexed_messages = 0
        for position, message in enumerate(conversation.messages, start=1):
            body = message.content.strip()
            if not body:
                continue
            message_id = message.message_id or f"message-{position}"
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, message_id, message_order,
                    author_role, author_name, created_at, content_type, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    message_id,
                    position,
                    message.role or "unknown",
                    message.author_name,
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
            indexed_messages += 1
            if position % 1000 == 0 or position == total_messages:
                _emit(
                    progress,
                    f"Indexed messages: {position}/{total_messages} scanned, {indexed_messages} with text.",
                )

        for category_name in conversation.category_hints:
            category = get_or_create_category(connection, category_name)
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
        _emit(progress, f"Committing message index for {conversation.conversation_id}…")
    _emit(progress, f"Canonical message index committed for {conversation.conversation_id}.")
    return True
