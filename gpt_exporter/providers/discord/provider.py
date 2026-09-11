"""Discord provider adapter for collector exports and native data packages."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage, ProviderDescriptor

from .naming import is_group_dm

_DESCRIPTOR = ProviderDescriptor(provider_id="discord", display_name="Discord", version="2")
_COLLECTOR_EXPORTER = "9c discord-exporter"


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _collector_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = _read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exporter") != _COLLECTOR_EXPORTER:
        return None
    if not isinstance(payload.get("conversation"), dict) or not isinstance(payload.get("messages"), list):
        return None
    return payload


def _lower_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key).casefold(): item for key, item in value.items()}


def _field(value: dict[str, Any], *names: str) -> Any:
    lowered = _lower_mapping(value)
    for name in names:
        if name.casefold() in lowered:
            return lowered[name.casefold()]
    return None


def _looks_like_message(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    lowered = _lower_mapping(value)
    return (
        "id" in lowered
        and "timestamp" in lowered
        and ("contents" in lowered or "content" in lowered)
    )


def _json_transcript(path: Path) -> list[dict[str, Any]] | None:
    try:
        payload = _read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    if not payload:
        return []
    if not all(isinstance(item, dict) for item in payload):
        return None
    return payload if _looks_like_message(payload[0]) else None


def _csv_transcript(path: Path) -> list[dict[str, Any]] | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
            fieldnames = tuple(reader.fieldnames or ())
    except (OSError, UnicodeError, csv.Error):
        return None
    lowered = {name.casefold() for name in fieldnames if name}
    if not {"id", "timestamp"}.issubset(lowered):
        return None
    if not ({"contents", "content"} & lowered):
        return None
    return rows


def _read_transcript(path: Path) -> tuple[list[dict[str, Any]], str]:
    if path.suffix.casefold() == ".json":
        rows = _json_transcript(path)
        if rows is not None:
            return rows, "json"
    if path.suffix.casefold() == ".csv":
        rows = _csv_transcript(path)
        if rows is not None:
            return rows, "csv"
    raise ValueError(f"Not a Discord message transcript: {path}")


def _metadata_candidates(transcript: Path) -> Iterable[dict[str, Any]]:
    for path in sorted(transcript.parent.glob("*.json")):
        if path == transcript:
            continue
        try:
            payload = _read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            yield payload


def _first_metadata(transcript: Path) -> dict[str, Any]:
    candidates = list(_metadata_candidates(transcript))
    for candidate in candidates:
        lowered = _lower_mapping(candidate)
        if any(key in lowered for key in ("channel_id", "channel id", "channel", "guild_id", "guild id")):
            return candidate
    return candidates[0] if candidates else {}


def _asset_from_url(message_id: str, index: int, source_ref: str, *, kind: str = "attachment", name: str | None = None, asset_id: str | None = None) -> CanonicalAsset:
    parsed = urlparse(source_ref)
    return CanonicalAsset(
        asset_id=asset_id or f"discord:{message_id}:{kind}:{index}",
        name=name or Path(parsed.path).name or f"{kind}-{index}",
        source_ref=source_ref,
        metadata={"provider": "discord", "kind": kind},
    )


def _collector_assets(message: dict[str, Any], message_id: str) -> tuple[CanonicalAsset, ...]:
    assets: list[CanonicalAsset] = []
    seen: set[str] = set()

    def add(url: Any, *, kind: str, name: str | None = None, asset_id: str | None = None) -> None:
        ref = _string(url)
        if not ref or ref in seen:
            return
        seen.add(ref)
        assets.append(_asset_from_url(message_id, len(assets) + 1, ref, kind=kind, name=name, asset_id=asset_id))

    raw_attachments = message.get("attachments")
    if isinstance(raw_attachments, list):
        for item in raw_attachments:
            if not isinstance(item, dict):
                continue
            attachment_id = _string(item.get("id"))
            add(
                item.get("original_url") or item.get("preview_url"),
                kind="attachment",
                name=_string(item.get("name")),
                asset_id=(f"discord:attachment:{attachment_id}" if attachment_id else None),
            )

    raw_media = message.get("linked_media")
    if isinstance(raw_media, list):
        for item in raw_media:
            if isinstance(item, dict):
                add(item.get("url"), kind=_string(item.get("kind")) or "linked-media")

    raw_previews = message.get("external_previews")
    if isinstance(raw_previews, list):
        for item in raw_previews:
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            if isinstance(image, dict):
                add(image.get("original_url") or image.get("proxy_url"), kind="external-preview")

    raw_stickers = message.get("stickers")
    if isinstance(raw_stickers, list):
        for item in raw_stickers:
            if isinstance(item, dict):
                add(item.get("url"), kind="sticker", name=_string(item.get("name")))
    return tuple(assets)


def _normalize_collector(path: Path, payload: dict[str, Any]) -> CanonicalConversation:
    conversation = payload["conversation"]
    assert isinstance(conversation, dict)
    channel_id = _string(conversation.get("channel_id"))
    if not channel_id:
        raise ValueError("Discord collector export has no channel ID")

    messages: list[CanonicalMessage] = []
    raw_messages = payload["messages"]
    assert isinstance(raw_messages, list)
    for index, raw in enumerate(raw_messages, start=1):
        if not isinstance(raw, dict):
            continue
        message_id = _string(raw.get("id")) or f"discord:{channel_id}:{index}"
        author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
        is_self = author.get("is_self")
        role = "user" if is_self is True else "other" if is_self is False else "unknown"
        metadata = {
            "provider": "discord",
            "edited": bool(raw.get("edited")),
            "content_type": raw.get("content_type"),
            "content_types": raw.get("content_types"),
            "mentions": raw.get("mentions"),
            "links": raw.get("links"),
            "reply": raw.get("reply"),
            "reactions": raw.get("reactions"),
            "resource_refs": raw.get("resource_refs"),
            "author_is_self": is_self,
            "author_detection": author.get("self_detection"),
        }
        messages.append(
            CanonicalMessage(
                message_id=message_id,
                role=role,
                content=_string(raw.get("content")) or "",
                created_at=_string(raw.get("timestamp")),
                author_id=_string(author.get("id")),
                author_name=_string(author.get("name")),
                assets=_collector_assets(raw, message_id),
                metadata={key: value for key, value in metadata.items() if value not in (None, [], {})},
            )
        )

    title = _string(conversation.get("title")) or f"Discord DM {channel_id}"
    conversation_metadata = {
        "source_kind": "browser_collector",
        "source_file": path.name,
        "schema_version": payload.get("schema_version"),
        "exported_at": payload.get("exported_at"),
        "source_url": payload.get("source_url"),
        "channel_id": channel_id,
        "conversation_type": conversation.get("type"),
        "participants": conversation.get("participants"),
        "current_user": payload.get("current_user"),
        "diagnostics": payload.get("diagnostics"),
        "resource_counts": (payload.get("resources") or {}).get("counts") if isinstance(payload.get("resources"), dict) else None,
    }
    group_dm = is_group_dm(conversation_metadata)
    if group_dm:
        conversation_metadata["conversation_type"] = "group_dm"

    return CanonicalConversation(
        conversation_id=f"discord:{channel_id}",
        provider_id="discord",
        title=title,
        messages=tuple(messages),
        created_at=(messages[0].created_at if messages else None),
        updated_at=(messages[-1].created_at if messages else None),
        category_hints=(("Discord Group DM",) if group_dm else ("Discord Direct Message",)),
        metadata=conversation_metadata,
    )


def _split_attachments(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        if not text:
            return ()
        items = [piece.strip() for piece in text.replace("\r", "\n").split("\n")]
        if len(items) == 1 and "," in items[0]:
            items = [piece.strip() for piece in items[0].split(",")]
    return tuple(str(item).strip() for item in items if str(item).strip())


def _conversation_title(metadata: dict[str, Any], conversation_id: str) -> str:
    channel_name = _string(_field(metadata, "channel_name", "channel name", "name", "channel"))
    guild_name = _string(_field(metadata, "guild_name", "guild name", "guild"))
    recipients = _field(metadata, "recipients", "recipient_ids", "user_ids", "users")
    if guild_name and channel_name:
        return f"{guild_name} / #{channel_name}"
    if channel_name:
        return channel_name
    if isinstance(recipients, list) and recipients:
        return "DM " + ", ".join(str(item) for item in recipients)
    return f"Discord channel {conversation_id}"


def _normalize_native(path: Path) -> CanonicalConversation:
    rows, transcript_format = _read_transcript(path)
    metadata = _first_metadata(path)
    channel_id = _string(_field(metadata, "channel_id", "channel id", "id")) or path.parent.name
    conversation_id = f"discord:{channel_id}"
    messages: list[CanonicalMessage] = []
    for index, row in enumerate(rows, start=1):
        message_id = _string(_field(row, "id")) or f"{conversation_id}:{index}"
        attachments = _split_attachments(_field(row, "attachments", "attachment"))
        messages.append(
            CanonicalMessage(
                message_id=message_id,
                role="user",
                content=_string(_field(row, "contents", "content", "message")) or "",
                created_at=_string(_field(row, "timestamp", "time", "created_at")),
                assets=tuple(
                    _asset_from_url(message_id, asset_index, ref)
                    for asset_index, ref in enumerate(attachments, start=1)
                ),
                metadata={"provider": "discord", "source_kind": "native_data_package"},
            )
        )
    return CanonicalConversation(
        conversation_id=conversation_id,
        provider_id="discord",
        title=_conversation_title(metadata, channel_id),
        messages=tuple(messages),
        created_at=(messages[0].created_at if messages else None),
        updated_at=(messages[-1].created_at if messages else None),
        metadata={
            "source_kind": "native_data_package",
            "channel_id": channel_id,
            "transcript_format": transcript_format,
            "source_file": path.name,
        },
    )


class DiscordProvider:
    """Normalize Discord browser collector exports and native package transcripts."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        return _DESCRIPTOR

    def discover(self, source: Path) -> Iterable[Path]:
        source = Path(source)
        if source.is_file():
            if _collector_payload(source) is not None:
                yield source
                return
            try:
                _read_transcript(source)
            except ValueError:
                return
            yield source
            return
        if not source.is_dir():
            return
        for path in sorted(source.rglob("*.json")):
            if _collector_payload(path) is not None:
                yield path
        messages_root = source / "messages"
        roots = (messages_root,) if messages_root.is_dir() else (source,)
        for root in roots:
            for path in sorted(root.rglob("*.json")):
                if _collector_payload(path) is None and _json_transcript(path) is not None:
                    yield path
            for path in sorted(root.rglob("*.csv")):
                if _csv_transcript(path) is not None:
                    yield path

    def normalize(self, source: Path) -> CanonicalConversation:
        path = Path(source)
        collector = _collector_payload(path)
        if collector is not None:
            return _normalize_collector(path, collector)
        return _normalize_native(path)
