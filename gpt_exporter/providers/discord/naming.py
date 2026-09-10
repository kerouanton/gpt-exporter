"""Human-facing naming helpers for Discord conversation artifacts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_NOTIFICATION_PREFIX = re.compile(r"^\(\d+\)\s+")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_filename_component(value: str, *, fallback: str = "unknown") -> str:
    text = _INVALID.sub("_", value).strip(" .")
    return text or fallback


def dm_self(metadata: Mapping[str, Any]) -> Mapping[str, Any] | None:
    current = metadata.get("current_user")
    if isinstance(current, dict):
        return current
    participants = metadata.get("participants")
    if isinstance(participants, list):
        for item in participants:
            if isinstance(item, dict) and item.get("is_self") is True:
                return item
    return None


def dm_peer(metadata: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return the other DM participant, even when Discord cannot resolve their user id."""
    participants = metadata.get("participants")
    if not isinstance(participants, list):
        return None

    candidates = [item for item in participants if isinstance(item, dict)]
    for item in candidates:
        if item.get("is_self") is False:
            return item

    local = dm_self(metadata)
    local_id = _text(local.get("id")) if local else None
    local_names: set[str] = set()
    if local:
        for key in ("username", "display_name", "name"):
            value = _text(local.get(key))
            if value:
                local_names.add(value.casefold().lstrip("@"))

    for item in candidates:
        if item.get("is_self") is True:
            continue
        item_id = _text(item.get("id"))
        if local_id and item_id and item_id == local_id:
            continue
        name = _text(item.get("username")) or _text(item.get("name")) or _text(item.get("display_name"))
        if not name:
            continue
        if name.casefold().lstrip("@") in local_names:
            continue
        return item
    return None


def _display_identity(record: Mapping[str, Any] | None, *, fallback: str) -> str:
    """Choose the same human-facing identity convention for both filename sides."""
    if not record:
        return fallback
    return (
        _text(record.get("display_name"))
        or _text(record.get("name"))
        or _text(record.get("username"))
        or fallback
    )


def dm_title(metadata: Mapping[str, Any], fallback_title: str) -> str:
    """Build the Browser title from the same two-sided identity convention as artifacts."""
    local = dm_self(metadata)
    peer = dm_peer(metadata)
    if local or peer:
        local_name = _display_identity(local, fallback="self").lstrip("@")
        peer_name = _display_identity(peer, fallback="peer").lstrip("@")
        return f"{local_name} ↔ {peer_name}"

    title = _NOTIFICATION_PREFIX.sub("", fallback_title).strip()
    if title.startswith("Discord |"):
        title = title.split("|", 1)[1].strip()
    return title or fallback_title


def dm_artifact_stem(metadata: Mapping[str, Any], channel_id: str) -> str:
    """Build a symmetric artifact stem using display names for both participants."""
    local_name = _display_identity(dm_self(metadata), fallback="self")
    peer_name = _display_identity(dm_peer(metadata), fallback="peer")
    local_name = safe_filename_component(local_name.lstrip("@"))
    peer_name = safe_filename_component(peer_name.lstrip("@"))
    return f"Discord DM {local_name} ↔ {peer_name} {channel_id}"


def discord_artifact_paths(root: Path, metadata: Mapping[str, Any], channel_id: str) -> tuple[Path, Path, Path]:
    """Return the canonical raw, canonical conversation and DOCX paths."""
    root = Path(root)
    stem = dm_artifact_stem(metadata, channel_id)
    downloads = root / "downloads"
    return (
        downloads / f"{stem}.raw.json.xz",
        downloads / f"{stem}.canonical.json.xz",
        root / f"{stem}.docx",
    )


def legacy_paths(root: Path, channel_id: str) -> tuple[Path, Path, Path]:
    return (
        root / f"Discord DM {channel_id}.docx",
        root / "raw" / f"discord_dm_{channel_id}.json",
        root / "downloads" / f"discord_dm_{channel_id}.json.xz",
    )


__all__ = [
    "discord_artifact_paths",
    "dm_artifact_stem",
    "dm_peer",
    "dm_self",
    "dm_title",
    "legacy_paths",
    "safe_filename_component",
]
