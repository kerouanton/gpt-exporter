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
    """Return the other 1:1 DM participant, even when Discord cannot resolve their user id."""
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


def _participant_records(metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    participants = metadata.get("participants")
    if not isinstance(participants, list):
        return []
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in participants:
        if not isinstance(item, dict):
            continue
        identity = (
            _text(item.get("id"))
            or _text(item.get("display_name"))
            or _text(item.get("name"))
            or _text(item.get("username"))
        )
        if not identity:
            continue
        key = identity.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    current = dm_self(metadata)
    if current:
        identity = (
            _text(current.get("id"))
            or _text(current.get("display_name"))
            or _text(current.get("name"))
            or _text(current.get("username"))
        )
        if identity and identity.casefold() not in seen:
            result.append(current)
    return result


def is_group_dm(metadata: Mapping[str, Any]) -> bool:
    """Identify Discord Group DMs without relying on the legacy collector type field."""
    if _text(metadata.get("conversation_type")) == "group_dm":
        return True
    records = _participant_records(metadata)
    non_self = [record for record in records if record.get("is_self") is not True]
    return len(records) > 2 or len(non_self) > 1


def _clean_discord_page_title(value: str) -> str:
    title = _NOTIFICATION_PREFIX.sub("", value).strip()
    if title.startswith("Discord |"):
        title = title.split("|", 1)[1].strip()
    return title


def _peer_name_from_fallback_title(fallback_title: str) -> str | None:
    """Recover a 1:1 DM peer from a normalized Browser title or Discord page title."""
    title = _clean_discord_page_title(fallback_title)
    if "↔" in title:
        peer = title.rsplit("↔", 1)[1].strip().lstrip("@")
        if peer and peer.casefold() not in {"peer", "unknown participant"}:
            return peer
    if not title.startswith("@"):
        return None
    name = title[1:].strip()
    if not name or any(character.isspace() for character in name):
        return None
    return name


def _ensure_peer_from_fallback_title(
    metadata: Mapping[str, Any], fallback_title: str
) -> Mapping[str, Any] | None:
    """Persist a title-derived peer only for unresolved 1:1 browser-collected DMs."""
    peer = dm_peer(metadata)
    if peer is not None:
        return peer
    if _text(metadata.get("conversation_type")) != "dm" or is_group_dm(metadata):
        return None
    name = _peer_name_from_fallback_title(fallback_title)
    if not name:
        return None

    fallback = {
        "id": None,
        "name": name,
        "username": name,
        "avatar_url": None,
        "is_self": False,
        "identity_source": "document-title-fallback",
    }
    if isinstance(metadata, dict):
        participants = metadata.get("participants")
        existing = list(participants) if isinstance(participants, list) else []
        metadata["participants"] = [*existing, fallback]
    return fallback


def _display_identity(record: Mapping[str, Any] | None, *, fallback: str) -> str:
    """Choose the same human-facing identity convention for filenames and titles."""
    if not record:
        return fallback
    return (
        _text(record.get("display_name"))
        or _text(record.get("name"))
        or _text(record.get("username"))
        or fallback
    )


def _group_participant_label(metadata: Mapping[str, Any]) -> str | None:
    names = []
    for record in _participant_records(metadata):
        if record.get("is_self") is True:
            continue
        name = _display_identity(record, fallback="").lstrip("@")
        if name and name not in names:
            names.append(name)
    return " · ".join(names) if names else None


def _group_name(metadata: Mapping[str, Any], fallback_title: str | None = None) -> str | None:
    explicit = _text(metadata.get("group_name"))
    if explicit:
        return explicit
    if fallback_title:
        title = _clean_discord_page_title(fallback_title)
        if title and not title.startswith("@") and "↔" not in title:
            return title
    return _group_participant_label(metadata)


def dm_title(metadata: Mapping[str, Any], fallback_title: str) -> str:
    """Build the Browser title for either a 1:1 DM or a Group DM."""
    if is_group_dm(metadata):
        group_name = _group_name(metadata, fallback_title) or "Discord Group DM"
        if isinstance(metadata, dict):
            metadata["conversation_type"] = "group_dm"
            metadata["group_name"] = group_name
        return group_name

    local = dm_self(metadata)
    peer = _ensure_peer_from_fallback_title(metadata, fallback_title)
    if local or peer:
        local_name = _display_identity(local, fallback="self").lstrip("@")
        peer_name = _display_identity(peer, fallback="peer").lstrip("@")
        return f"{local_name} ↔ {peer_name}"

    title = _clean_discord_page_title(fallback_title)
    return title or fallback_title


def dm_artifact_stem(metadata: Mapping[str, Any], channel_id: str) -> str:
    """Build a stable human-facing artifact stem for Discord DMs and Group DMs."""
    if is_group_dm(metadata):
        group_name = _group_name(metadata) or "group"
        group_name = safe_filename_component(group_name)
        return f"Discord Group DM {group_name} {channel_id}"

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
    "is_group_dm",
    "legacy_paths",
    "safe_filename_component",
]
