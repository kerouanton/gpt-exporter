"""Discord data-package provider adapter for the provider-neutral core model."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from gpt_exporter.core import (
    CanonicalAsset,
    CanonicalConversation,
    CanonicalMessage,
    ProviderDescriptor,
)


_DESCRIPTOR = ProviderDescriptor(
    provider_id="discord",
    display_name="Discord",
    version="1",
)


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
    has_id = "id" in lowered
    has_timestamp = "timestamp" in lowered
    has_content = "contents" in lowered or "content" in lowered
    return has_id and has_timestamp and has_content


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
    if not _looks_like_message(payload[0]):
        return None
    return payload


def _csv_transcript(path: Path) -> list[dict[str, Any]] | None:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error):
        return None
    if not reader.fieldnames:
        return None
    lowered = {name.casefold() for name in reader.fieldnames if name}
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
    elif path.suffix.casefold() == ".csv":
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
    if not candidates:
        return {}
    for candidate in candidates:
        lowered = _lower_mapping(candidate)
        if any(
            key in lowered
            for key in ("channel_id", "channel id", "channel", "guild_id", "guild id")
        ):
            return candidate
    return candidates[0]


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _attachment_asset(message_id: str, index: int, source_ref: str) -> CanonicalAsset:
    parsed = urlparse(source_ref)
    name = Path(parsed.path).name or f"attachment-{index}"
    return CanonicalAsset(
        asset_id=f"discord:{message_id}:attachment:{index}",
        name=name,
        source_ref=source_ref,
        metadata={"provider": "discord", "kind": "attachment"},
    )


def _conversation_title(metadata: dict[str, Any], conversation_id: str) -> str:
    channel_name = _string(
        _field(metadata, "channel_name", "channel name", "name", "channel")
    )
    guild_name = _string(_field(metadata, "guild_name", "guild name", "guild"))
    recipients = _field(metadata, "recipients", "recipient_ids", "user_ids", "users")
    if guild_name and channel_name:
        return f"{guild_name} / #{channel_name}"
    if channel_name:
        return channel_name
    if isinstance(recipients, list) and recipients:
        return "DM " + ", ".join(str(item) for item in recipients)
    return f"Discord channel {conversation_id}"


class DiscordProvider:
    """Normalize Discord native data-package message transcripts.

    Discord's native data package contains only messages sent by the requesting
    account. Consequently normalized transcript messages are represented as
    ``role='user'``; the provider does not invent missing messages from other
    participants.
    """

    @property
    def descriptor(self) -> ProviderDescriptor:
        return _DESCRIPTOR

    def discover(self, source: Path) -> Iterable[Path]:
        source = Path(source)
        if source.is_file():
            try:
                _read_transcript(source)
            except ValueError:
                return
            yield source
            return
        if not source.is_dir():
            return

        messages_root = source / "messages"
        roots = (messages_root,) if messages_root.is_dir() else (source,)
        for root in roots:
            for path in sorted(root.rglob("*.json")):
                if _json_transcript(path) is not None:
                    yield path
            for path in sorted(root.rglob("*.csv")):
                if _csv_transcript(path) is not None:
                    yield path

    def normalize(self, source: Path) -> CanonicalConversation:
        source = Path(source)
        rows, transcript_format = _read_transcript(source)
        metadata = _first_metadata(source)

        channel_id = _string(
            _field(metadata, "channel_id", "channel id", "id")
        ) or source.parent.name
        conversation_id = f"discord:{channel_id}"

        messages: list[CanonicalMessage] = []
        for index, row in enumerate(rows, start=1):
            message_id = _string(_field(row, "id")) or f"{conversation_id}:{index}"
            timestamp = _string(_field(row, "timestamp", "time", "created_at"))
            content = _string(_field(row, "contents", "content", "message")) or ""
            attachments = _split_attachments(_field(row, "attachments", "attachment"))
            assets = tuple(
                _attachment_asset(message_id, asset_index, ref)
                for asset_index, ref in enumerate(attachments, start=1)
            )
            messages.append(
                CanonicalMessage(
                    message_id=message_id,
                    role="user",
                    content=content,
                    created_at=timestamp,
                    assets=assets,
                    metadata={"provider": "discord"},
                )
            )

        provider_metadata = {
            "channel_id": channel_id,
            "channel_name": _string(_field(metadata, "channel_name", "channel name", "name")),
            "guild_id": _string(_field(metadata, "guild_id", "guild id")),
            "guild_name": _string(_field(metadata, "guild_name", "guild name", "guild")),
            "recipient_ids": _field(metadata, "recipient_ids", "user_ids", "recipients", "users"),
            "transcript_format": transcript_format,
            "source_file": source.name,
        }
        provider_metadata = {
            key: value for key, value in provider_metadata.items() if value not in (None, "")
        }

        created_at = messages[0].created_at if messages else None
        updated_at = messages[-1].created_at if messages else None
        return CanonicalConversation(
            conversation_id=conversation_id,
            provider_id=_DESCRIPTOR.provider_id,
            title=_conversation_title(metadata, channel_id),
            messages=tuple(messages),
            created_at=created_at,
            updated_at=updated_at,
            metadata=provider_metadata,
        )
