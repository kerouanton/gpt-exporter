"""Normalize preserved ChatGPT conversation JSON into the common model.

The v2.8 visibility/active-path rules remain the behavioral authority during the
refactor. This adapter reuses them rather than reimplementing ChatGPT semantics
while the generic model/index/export layers are introduced.
"""

from __future__ import annotations

import contextlib
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gpt_exporter.model import Attachment, ContentBlock, Conversation, Message, Participant


with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.export import _legacy_markdown as legacy


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _raw_messages_by_node(active_path: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in active_path:
        node_id = node.get("id")
        message = node.get("message")
        if isinstance(node_id, str) and isinstance(message, dict):
            result[node_id] = message
    return result


def _native_attachments(message: dict[str, Any]) -> tuple[Attachment, ...]:
    attachments: list[Attachment] = []
    seen: set[str] = set()

    metadata = message.get("metadata")
    if isinstance(metadata, dict):
        native = metadata.get("attachments")
        if isinstance(native, list):
            for item in native:
                if not isinstance(item, dict):
                    continue
                identifier = item.get("id") or item.get("file_id")
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                attachments.append(
                    Attachment(
                        attachment_id=identifier,
                        filename=str(item.get("name") or ""),
                        media_type=str(item.get("mime_type") or ""),
                        metadata={"chatgpt": dict(item)},
                    )
                )

    content = message.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("content_type") or "")
            if part_type not in {
                "image_asset_pointer",
                "audio_asset_pointer",
                "file_asset_pointer",
            }:
                continue
            pointer = (
                part.get("asset_pointer")
                or part.get("pointer")
                or part.get("file_id")
                or part.get("url")
            )
            identifier = legacy.extract_file_id(pointer)
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            attachments.append(
                Attachment(
                    attachment_id=identifier,
                    source_url=str(pointer or ""),
                    metadata={"chatgpt": dict(part)},
                )
            )

    return tuple(attachments)


def normalize_conversation_file(
    input_path: Path | str,
    *,
    asset_directory: Path | str | None = None,
    markdown_directory: Path | str | None = None,
) -> Conversation:
    """Normalize one preserved ChatGPT JSON/XZ conversation.

    Text extraction deliberately reuses the frozen exporter behavior. Native
    metadata is retained on normalized records so later core features can grow
    without requiring destructive changes to the preserved source archive.
    """

    source = Path(input_path).expanduser().resolve()
    data = legacy.load_json(source)
    mapping = data["mapping"]
    current_node_id = data["current_node"]
    active_path = legacy.reconstruct_active_path(mapping, current_node_id)
    raw_by_node = _raw_messages_by_node(active_path)

    assets_root = (
        Path(asset_directory).expanduser().resolve()
        if asset_directory is not None
        else source.parent.parent / "assets"
    )
    markdown_root = (
        Path(markdown_directory).expanduser().resolve()
        if markdown_directory is not None
        else source.parent.parent / "markdown"
    )

    statistics = legacy.ExportStatistics()
    assets = legacy.discover_local_assets(assets_root) if assets_root.is_dir() else {}
    visible = legacy.extract_visible_messages(
        active_path=active_path,
        statistics=statistics,
        assets=assets,
        asset_directory=assets_root,
        markdown_directory=markdown_root,
    )

    messages: list[Message] = []
    participants: dict[str, Participant] = {}

    for exported in visible:
        native_message = raw_by_node.get(exported.node_id, {})
        author = native_message.get("author")
        author = author if isinstance(author, dict) else {}
        author_role = str(exported.role or author.get("role") or "")
        author_name = str(author.get("name") or "")
        author_id = str(author.get("name") or author_role or "unknown")

        if author_id not in participants:
            participants[author_id] = Participant(
                participant_id=author_id,
                display_name=author_name,
                role=author_role,
                metadata={"chatgpt": dict(author)} if author else {},
            )

        messages.append(
            Message(
                message_id=exported.node_id,
                author_id=author_id,
                author_name=author_name,
                author_role=author_role,
                created_at=_timestamp(exported.create_time),
                edited_at=_timestamp(exported.update_time),
                text=exported.text,
                content=(
                    ContentBlock(
                        kind=exported.content_type,
                        text=exported.text,
                    ),
                ),
                attachments=_native_attachments(native_message),
                metadata={
                    "chatgpt": {
                        "node_id": exported.node_id,
                        "native_message": native_message,
                    }
                },
            )
        )

    return Conversation(
        provider_key="chatgpt",
        conversation_id=str(data.get("conversation_id") or "unknown"),
        title=str(data.get("title") or "Untitled conversation"),
        created_at=_timestamp(data.get("create_time")),
        updated_at=_timestamp(data.get("update_time")),
        participants=tuple(participants.values()),
        messages=tuple(messages),
        metadata={
            "chatgpt": {
                "current_node": current_node_id,
                "source_path": str(source),
                "all_nodes": len(mapping),
                "active_nodes": len(active_path),
                "export_statistics": {
                    "exported_messages": statistics.exported_messages,
                    "skipped_reasons": dict(statistics.skipped_reasons),
                },
            }
        },
    )


__all__ = ["normalize_conversation_file"]
