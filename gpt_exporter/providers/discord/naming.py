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
    """Return the other DM participant, even when Discord cannot resolve their user id.

    The collector can reliably identify the local account while the peer may have
    ``is_self=None`` (for example older messages or users whose author id is not
    available from the rendered DOM).  Treating the first participant as a fallback
    can therefore select the local user and rename the conversation after ourselves.
    Prefer explicit non-self entries, then any named participant that is not the
    identified local account.
    """
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


def dm_title(metadata: Mapping[str, Any], fallback_title: str) -> str:
    peer = dm_peer(metadata)
    peer_name = _text(peer.get("name")) if peer else None
    if not peer_name and peer:
        peer_name = _text(peer.get("display_name")) or _text(peer.get("username"))
    if peer_name:
        return peer_name if peer_name.startswith("@") else f"@{peer_name}"
    title = _NOTIFICATION_PREFIX.sub("", fallback_title).strip()
    if title.startswith("Discord |"):
        title = title.split("|", 1)[1].strip()
    return title or fallback_title


def dm_artifact_stem(metadata: Mapping[str, Any], channel_id: str) -> str:
    local = dm_self(metadata)
    peer = dm_peer(metadata)
    local_name = None
    if local:
        local_name = _text(local.get("username")) or _text(local.get("display_name")) or _text(local.get("name"))
    peer_name = _text(peer.get("username")) if peer else None
    if not peer_name and peer:
        peer_name = _text(peer.get("name")) or _text(peer.get("display_name"))
    local_name = safe_filename_component((local_name or "self").lstrip("@"))
    peer_name = safe_filename_component((peer_name or "peer").lstrip("@"))
    return f"Discord DM {local_name} ↔ {peer_name} {channel_id}"


def legacy_paths(root: Path, channel_id: str) -> tuple[Path, Path, Path]:
    return (
        root / f"Discord DM {channel_id}.docx",
        root / "raw" / f"discord_dm_{channel_id}.json",
        root / "downloads" / f"discord_dm_{channel_id}.json.xz",
    )


__all__ = ["dm_artifact_stem", "dm_peer", "dm_self", "dm_title", "legacy_paths", "safe_filename_component"]
