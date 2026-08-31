"""Normalize preserved ChatGPT conversation JSON into the common model.

The existing GPT Exporter behavior remains authoritative during the refactor.
ChatGPT has two intentionally different message projections:

* display/export follows the active branch and the frozen Markdown rules;
* search/index follows the historical SQLite indexer's mapping-wide rules.

The common model stores the union and marks each message with independent
display/search semantics so the core can reproduce both behaviors exactly.
"""

from __future__ import annotations

import contextlib
import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from gpt_exporter.model import (
    Attachment,
    ContentBlock,
    Conversation,
    ConversationOrigin,
    Message,
    Participant,
)


with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.export import _legacy_markdown as legacy


_INDEXABLE_ROLES = {"user", "assistant"}
_EXCLUDED_INDEX_CONTENT_TYPES = {
    "user_editable_context",
    "model_editable_context",
    "thoughts",
    "reasoning_recap",
}
_WHITESPACE_RE = re.compile(r"\s+")
_ORIGIN_TYPE_PRIORITY = {"project": 0, "custom_gpt": 1, "other": 2}


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _classify_origin_id(origin_id: str) -> str:
    if origin_id.startswith("g-p-"):
        return "project"
    if origin_id.startswith("g-"):
        return "custom_gpt"
    return "other"


def _iter_nested_gizmo_ids(value: Any, path: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "gizmo_id":
                candidate = _optional_string(child)
                if candidate:
                    yield candidate, child_path
            if isinstance(child, (dict, list)):
                yield from _iter_nested_gizmo_ids(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                yield from _iter_nested_gizmo_ids(child, f"{path}[{index}]")


def _conversation_origins(data: dict[str, Any]) -> tuple[ConversationOrigin, ...]:
    """Mirror the historical native origin detection provider-side."""

    discovered: dict[str, dict[str, str]] = {}

    def add(origin_id: str | None, source: str) -> None:
        if not origin_id:
            return
        current = discovered.get(origin_id)
        if current is None:
            discovered[origin_id] = {
                "origin_id": origin_id,
                "origin_type": _classify_origin_id(origin_id),
                "source": source,
            }
        elif source not in current["source"].split(";"):
            current["source"] += ";" + source

    add(_optional_string(data.get("gizmo_id")), "top_level.gizmo_id")
    add(
        _optional_string(data.get("conversation_template_id")),
        "top_level.conversation_template_id",
    )

    mapping = data.get("mapping") or {}
    if isinstance(mapping, dict):
        for node in mapping.values():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not isinstance(message, dict):
                continue

            metadata = message.get("metadata")
            if isinstance(metadata, (dict, list)):
                for origin_id, path in _iter_nested_gizmo_ids(
                    metadata, "message.metadata"
                ):
                    add(origin_id, path)

            content = message.get("content")
            if isinstance(content, dict):
                for origin_id, path in _iter_nested_gizmo_ids(
                    content, "message.content"
                ):
                    add(origin_id, path)

    ordered = sorted(
        discovered.values(),
        key=lambda item: (
            _ORIGIN_TYPE_PRIORITY[item["origin_type"]],
            item["origin_id"],
        ),
    )
    return tuple(
        ConversationOrigin(
            origin_id=item["origin_id"],
            origin_type=item["origin_type"],
            source=item["source"],
        )
        for item in ordered
    )


def _index_normalize_text(value: Any) -> str:
    """Mirror the v2.9 indexer's searchable-text normalization exactly."""
    if value is None:
        return ""
    if isinstance(value, str):
        return _WHITESPACE_RE.sub(" ", value).strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(
            filter(None, (_index_normalize_text(item) for item in value))
        ).strip()
    if isinstance(value, dict):
        if "text" in value:
            return _index_normalize_text(value["text"])
        if "parts" in value:
            return _index_normalize_text(value["parts"])
    return ""


def _index_message_text(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    if not isinstance(content, dict):
        return ""
    content_type = content.get("content_type")
    if content_type in {"text", "code", "multimodal_text"}:
        return _index_normalize_text(content.get("parts"))
    return _index_normalize_text(content.get("text") or content.get("parts"))


def _is_indexable_message(message: dict[str, Any]) -> bool:
    """Mirror the historical SQLite indexer's visibility/search predicate."""
    author = message.get("author") or {}
    role = author.get("role") if isinstance(author, dict) else None
    if role not in _INDEXABLE_ROLES:
        return False

    metadata = message.get("metadata") or {}
    if isinstance(metadata, dict) and metadata.get("is_visually_hidden_from_conversation"):
        return False

    content = message.get("content") or {}
    if not isinstance(content, dict):
        return False
    if content.get("content_type") in _EXCLUDED_INDEX_CONTENT_TYPES:
        return False

    return bool(_index_message_text(message))


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


def _display_name(role: str, native_name: str) -> str:
    # The frozen ChatGPT Markdown exporter presents visible tool output as
    # ChatGPT, even when native author.name contains an internal tool name
    # such as file_search, api_tool, or an opaque tool identifier. Keep the
    # native name in provider metadata/participant identity, but preserve the
    # historical visible label for export parity.
    if role == "tool":
        return "ChatGPT"
    if native_name.strip():
        return native_name.strip()
    if role == "user":
        return "Bruno"
    if role == "assistant":
        return "ChatGPT"
    return role.capitalize() if role else "Unknown"


def _participant(
    participants: dict[str, Participant],
    *,
    role: str,
    native_name: str,
    author: dict[str, Any],
) -> tuple[str, str]:
    display_name = _display_name(role, native_name)
    participant_id = str(native_name or role or "unknown")
    if participant_id not in participants:
        participants[participant_id] = Participant(
            participant_id=participant_id,
            display_name=display_name,
            role=role,
            metadata={"chatgpt": dict(author)} if author else {},
        )
    return participant_id, display_name


def normalize_conversation_file(
    input_path: Path | str,
    *,
    asset_directory: Path | str | None = None,
    markdown_directory: Path | str | None = None,
) -> Conversation:
    """Normalize one preserved ChatGPT JSON/XZ conversation.

    Display text deliberately reuses the frozen Markdown exporter. Search text
    deliberately mirrors the frozen SQLite indexer. Native metadata is retained
    so the normalized representation stays rebuildable and non-destructive.
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

    participants: dict[str, Participant] = {}
    records: dict[str, dict[str, Any]] = {}
    record_order: list[str] = []

    def ensure_record(key: str) -> dict[str, Any]:
        record = records.get(key)
        if record is None:
            record = {
                "key": key,
                "native_message": {},
                "display": None,
                "display_order": None,
                "search_text": "",
                "search_order": None,
            }
            records[key] = record
            record_order.append(key)
        return record

    for display_order, exported in enumerate(visible, start=1):
        native_message = raw_by_node.get(exported.node_id, {})
        native_id = native_message.get("id") if isinstance(native_message, dict) else None
        key = str(native_id or exported.node_id)
        record = ensure_record(key)
        record["native_message"] = native_message
        record["display"] = exported
        record["display_order"] = display_order

    searchable_native: list[dict[str, Any]] = []
    for node in mapping.values():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if isinstance(message, dict) and _is_indexable_message(message):
            searchable_native.append(message)

    for search_order, native_message in enumerate(searchable_native, start=1):
        native_id = native_message.get("id")
        key = str(native_id or f"message-{search_order}")
        record = ensure_record(key)
        if not record["native_message"]:
            record["native_message"] = native_message
        record["search_text"] = _index_message_text(native_message)
        record["search_order"] = search_order

    messages: list[Message] = []
    for key in record_order:
        record = records[key]
        native_message = record["native_message"]
        native_message = native_message if isinstance(native_message, dict) else {}
        exported = record["display"]

        author = native_message.get("author")
        author = author if isinstance(author, dict) else {}
        native_role = str(author.get("role") or "")
        display_role = str(exported.role) if exported is not None else native_role
        role = display_role or native_role
        native_name = str(author.get("name") or "")
        author_id, author_name = _participant(
            participants,
            role=role,
            native_name=native_name,
            author=author,
        )

        content = native_message.get("content")
        native_content_type = (
            str(content.get("content_type") or "unknown")
            if isinstance(content, dict)
            else "unknown"
        )
        display_text = exported.text if exported is not None else record["search_text"]
        content_type = (
            str(exported.content_type)
            if exported is not None
            else native_content_type
        )
        display_node_id = exported.node_id if exported is not None else None

        messages.append(
            Message(
                message_id=key,
                author_id=author_id,
                author_name=author_name,
                author_role=role,
                created_at=_timestamp(
                    exported.create_time if exported is not None else native_message.get("create_time")
                ),
                edited_at=_timestamp(
                    exported.update_time if exported is not None else native_message.get("update_time")
                ),
                text=str(display_text or ""),
                search_text=str(record["search_text"] or ""),
                is_visible=exported is not None,
                is_indexable=record["search_order"] is not None,
                display_order=record["display_order"],
                search_order=record["search_order"],
                content=(ContentBlock(kind=content_type, text=str(display_text or "")),),
                attachments=_native_attachments(native_message),
                metadata={
                    "chatgpt": {
                        "node_id": display_node_id,
                        "display_node_id": display_node_id,
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
        origins=_conversation_origins(data),
        index_metadata={
            "gizmo_id": _optional_string(data.get("gizmo_id")),
            "gizmo_type": _optional_string(data.get("gizmo_type")),
            "conversation_template_id": _optional_string(
                data.get("conversation_template_id")
            ),
            "conversation_origin": _optional_string(data.get("conversation_origin")),
            "default_model_slug": _optional_string(data.get("default_model_slug")),
        },
        metadata={
            "chatgpt": {
                "current_node": current_node_id,
                "source_path": str(source),
                "all_nodes": len(mapping),
                "active_nodes": len(active_path),
                "display_messages": len(visible),
                "indexable_messages": len(searchable_native),
                "export_statistics": {
                    "exported_messages": statistics.exported_messages,
                    "skipped_reasons": dict(statistics.skipped_reasons),
                },
            }
        },
    )


__all__ = ["normalize_conversation_file"]
