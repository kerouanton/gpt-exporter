"""ChatGPT-native indexing adapter for the provider-neutral index engine."""

from __future__ import annotations

import contextlib
import io
import logging
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from gpt_exporter.index.engine import (
    IndexUpdateResult,
    rebuild_index as rebuild_generic_index,
    update_index as update_generic_index,
)
from gpt_exporter.index.storage import delete_message_index_rows, now_iso, upsert_provider_metadata


LOGGER = logging.getLogger("chatgpt_archive_indexer")


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        from . import _native_indexer
    return _native_indexer


def _chatgpt_metadata(implementation: ModuleType, conversation: dict) -> dict[str, str]:
    fields = (
        "gizmo_id",
        "gizmo_type",
        "conversation_template_id",
        "conversation_origin",
        "default_model_slug",
    )
    result: dict[str, str] = {}
    for field in fields:
        value = implementation.optional_string(conversation.get(field))
        if value is not None:
            result[field] = value
    return result


def index_native_conversation(
    connection,
    json_path: Path,
    archive_root: Path,
    *,
    force: bool = False,
) -> bool:
    """Index one native ChatGPT conversation into provider-neutral schema v5."""
    implementation = _implementation()
    json_path = Path(json_path)
    archive_root = Path(archive_root)
    source_mtime_ns = json_path.stat().st_mtime_ns
    conversation = implementation.read_conversation(json_path)
    conversation_id = conversation["conversation_id"]

    existing = connection.execute(
        "SELECT source_mtime_ns FROM conversations WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    if not force and existing and existing["source_mtime_ns"] == source_mtime_ns:
        return False

    title = implementation.normalize_text(conversation.get("title")) or "Untitled conversation"
    docx = implementation.find_docx(archive_root, conversation_id)
    indexed_at = now_iso()
    visible_messages = list(implementation.conversation_messages(conversation))
    origins = implementation.detect_origins(conversation)
    primary_type, primary_id = implementation.primary_origin(origins)

    with connection:
        connection.execute(
            """
            INSERT INTO conversations (
                conversation_id, title, created_at, updated_at,
                source_json_path, source_mtime_ns, docx_path, indexed_at,
                primary_origin_type, primary_origin_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                title = excluded.title,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                source_json_path = excluded.source_json_path,
                source_mtime_ns = excluded.source_mtime_ns,
                docx_path = excluded.docx_path,
                indexed_at = excluded.indexed_at,
                primary_origin_type = excluded.primary_origin_type,
                primary_origin_id = excluded.primary_origin_id
            """,
            (
                conversation_id,
                title,
                implementation.iso_datetime(conversation.get("create_time")),
                implementation.iso_datetime(conversation.get("update_time")),
                str(json_path),
                source_mtime_ns,
                str(docx) if docx else None,
                indexed_at,
                primary_type,
                primary_id,
            ),
        )

        upsert_provider_metadata(
            connection,
            conversation_id,
            "gpt",
            _chatgpt_metadata(implementation, conversation),
        )
        delete_message_index_rows(connection, conversation_id)
        implementation.replace_detected_origins(connection, conversation_id, origins, primary_id)

        for position, message in enumerate(visible_messages, start=1):
            body = implementation.extract_message_text(message)
            message_id = message.get("id", f"message-{position}")
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
                    message.get("author", {}).get("role", "unknown"),
                    implementation.iso_datetime(message.get("create_time")),
                    message.get("content", {}).get("content_type"),
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


def update_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    force: bool = False,
    progress=None,
) -> IndexUpdateResult:
    return update_generic_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        force=force,
        progress=progress,
        native_indexer=index_native_conversation,
    )


def rebuild_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    progress=None,
) -> IndexUpdateResult:
    return rebuild_generic_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        progress=progress,
        native_indexer=index_native_conversation,
    )


__all__ = ["IndexUpdateResult", "index_native_conversation", "rebuild_index", "update_index"]
