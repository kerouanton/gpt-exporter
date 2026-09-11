"""Provider-owned archive workflow for Discord collector exports."""

from __future__ import annotations

import json
import lzma
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from gpt_exporter.core import CanonicalAsset
from gpt_exporter.core.serialization import (
    read_canonical_conversation,
    write_canonical_conversation,
)
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown
from gpt_exporter.index import update_index

from .assets import conversation_with_local_assets, download_conversation_assets
from .docx_parts import conversation_for_part, docx_paths_for_parts, plan_docx_parts
from .history import merge_dm_history
from .naming import discord_artifact_paths, dm_title, legacy_paths
from .provider import DiscordProvider
from .raw_archive import materialize_raw_json, read_raw_json, write_raw_archive


ProgressCallback = Callable[[str], None]
_PARTICIPANT_AVATAR_PREFIX = "Conversation participant avatar: "


@dataclass(frozen=True, slots=True)
class DiscordArchiveResult:
    archive_root: Path
    raw_path: Path
    canonical_path: Path
    docx_path: Path
    database_path: Path
    message_count: int
    updated: bool
    available_assets: int = 0
    downloaded_assets: int = 0
    reused_assets: int = 0
    failed_assets: tuple[str, ...] = ()
    docx_paths: tuple[Path, ...] = ()


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def default_archive_root() -> Path:
    return Path.home() / "Documents" / "Discord Archive"


def _channel_id(conversation_id: str) -> str:
    prefix = "discord:"
    return conversation_id[len(prefix):] if conversation_id.startswith(prefix) else conversation_id


def _avatar_media_type(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix.casefold()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(suffix)


def _collector_semantics(source_path: Path | None) -> dict[str, dict]:
    """Read provider-rich presentation metadata without polluting the shared core."""
    if source_path is None:
        return {}
    try:
        payload = read_raw_json(source_path)
    except (OSError, UnicodeError, json.JSONDecodeError, lzma.LZMAError):
        return {}
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if not isinstance(messages, list):
        return {}
    result: dict[str, dict] = {}
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        message_id = str(raw.get("id") or "").strip()
        if not message_id:
            continue
        semantics: dict[str, object] = {}
        previews = raw.get("external_previews")
        if isinstance(previews, list) and previews:
            semantics["link_previews"] = previews
            semantics["link_preview_image_indices"] = [
                index
                for index, preview in enumerate(previews)
                if isinstance(preview, dict) and isinstance(preview.get("image"), dict)
            ]
        result[message_id] = semantics
    return result


def _tag_preview_assets(
    assets: tuple[CanonicalAsset, ...],
    image_indices: object,
) -> tuple[CanonicalAsset, ...]:
    indices = list(image_indices) if isinstance(image_indices, list) else []
    next_index = 0
    tagged: list[CanonicalAsset] = []
    for asset in assets:
        if asset.metadata.get("kind") == "external-preview" and next_index < len(indices):
            preview_index = indices[next_index]
            next_index += 1
            if isinstance(preview_index, int) and preview_index >= 0:
                asset_metadata = dict(asset.metadata)
                asset_metadata["link_preview_index"] = preview_index
                asset = replace(asset, metadata=asset_metadata)
        tagged.append(asset)
    return tuple(tagged)


def _enrich_dm(conversation, *, source_path: Path | None = None):
    """Add human title/origin, chat semantics and reusable author-avatar assets."""
    metadata = dict(conversation.metadata)
    channel_id = _channel_id(conversation.conversation_id)
    metadata["origin_type"] = "Direct Messages"
    metadata["origin_id"] = channel_id
    semantic_by_message = _collector_semantics(source_path)

    authors: dict[str, dict] = {}
    participants = metadata.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if isinstance(participant, dict) and participant.get("id"):
                authors[str(participant["id"])] = participant
    current = metadata.get("current_user")
    if isinstance(current, dict) and current.get("id"):
        merged = dict(authors.get(str(current["id"]), {}))
        merged.update({key: value for key, value in current.items() if value is not None})
        authors[str(current["id"])] = merged

    messages = []
    for message in conversation.messages:
        author = authors.get(str(message.author_id or ""), {})
        avatar_url = str(author.get("avatar_url") or "").strip()
        assets = tuple(
            asset for asset in message.assets
            if asset.metadata.get("kind") != "author-avatar"
        )
        semantics = dict(semantic_by_message.get(message.message_id, {}))
        assets = _tag_preview_assets(
            assets,
            semantics.pop("link_preview_image_indices", []),
        )
        if avatar_url:
            author_id = str(message.author_id or "unknown")
            suffix = Path(urlparse(avatar_url).path).suffix or ".img"
            avatar = CanonicalAsset(
                asset_id=f"discord:author-avatar:{author_id}",
                name=f"avatar-{author_id}{suffix}",
                media_type=_avatar_media_type(avatar_url),
                source_ref=avatar_url,
                metadata={
                    "provider": "discord",
                    "kind": "author-avatar",
                    "author_id": author_id,
                    "author_name": message.author_name,
                },
            )
            assets = (avatar,) + assets

        message_metadata = dict(message.metadata)
        message_metadata["preserve_line_breaks"] = True
        message_metadata.update(semantics)
        messages.append(replace(message, assets=assets, metadata=message_metadata))

    return replace(
        conversation,
        title=dm_title(metadata, conversation.title),
        messages=tuple(messages),
        metadata=metadata,
    )


def _record_docx_path(database_path: Path, conversation_id: str, docx_path: Path) -> None:
    if not docx_path.is_file() or docx_path.stat().st_size == 0:
        return
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            "UPDATE conversations SET docx_path = ? WHERE conversation_id = ?",
            (str(docx_path), conversation_id),
        )
        connection.commit()


def _human_named_paths(directory: Path, channel_id: str, suffix: str) -> tuple[Path, ...]:
    """Find current and historical human-named artifacts by stable channel ID."""
    matches: set[Path] = set()
    for prefix in ("Discord DM ", "Discord Group DM "):
        matches.update(directory.glob(f"{prefix}* {channel_id}*{suffix}"))
    return tuple(sorted(matches))


def _human_named_docx_paths(directory: Path, channel_id: str) -> tuple[Path, ...]:
    """Include 1:1/group, legacy single DOCX and time-suffixed multipart DOCX files."""
    return _human_named_paths(directory, channel_id, ".docx")


def _canonical_candidates(downloads_dir: Path, channel_id: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in _human_named_paths(downloads_dir, channel_id, ".json.xz")
        if not path.name.casefold().endswith(".raw.json.xz")
    )


def _find_existing_canonical(downloads_dir: Path, channel_id: str, preferred: Path, legacy: Path):
    candidates: list[Path] = []
    for path in (preferred, legacy, *_canonical_candidates(downloads_dir, channel_id)):
        if path not in candidates and path.is_file() and path.stat().st_size > 0:
            candidates.append(path)

    best_path: Path | None = None
    best_conversation = None
    best_size = -1
    for path in candidates:
        try:
            candidate = _enrich_dm(read_canonical_conversation(path))
        except (OSError, ValueError):
            continue
        if candidate.conversation_id != f"discord:{channel_id}":
            continue
        size = len({message.message_id for message in candidate.messages})
        if size > best_size:
            best_path = path
            best_conversation = candidate
            best_size = size
    return best_path, best_conversation


def _find_prior_artifact(directory: Path, channel_id: str, suffix: str, legacy: Path) -> Path | None:
    candidates = []
    if legacy.is_file():
        candidates.append(legacy)
    candidates.extend(_human_named_paths(directory, channel_id, suffix))
    return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None


def _remove_stale_artifacts(root: Path, channel_id: str, *, keep: set[Path]) -> None:
    legacy_docx, legacy_raw, legacy_canonical = legacy_paths(root, channel_id)
    candidates = [legacy_docx, legacy_raw, legacy_canonical]
    candidates.extend(_human_named_docx_paths(root, channel_id))
    candidates.extend(_human_named_paths(root / "raw", channel_id, ".json"))
    candidates.extend(_human_named_paths(root / "raw", channel_id, ".json.xz"))
    candidates.extend(_human_named_paths(root / "downloads", channel_id, ".json.xz"))
    keep_resolved = {path.resolve() for path in keep}
    for path in candidates:
        try:
            if path.resolve() not in keep_resolved:
                path.unlink(missing_ok=True)
        except OSError:
            pass
    raw_dir = root / "raw"
    if raw_dir.is_dir():
        try:
            raw_dir.rmdir()
        except OSError:
            pass


def _without_author_avatars(conversation):
    """Keep author avatars in the archive, but omit them from message-body rendering."""
    messages = []
    for message in conversation.messages:
        assets = tuple(
            asset for asset in message.assets
            if str(asset.metadata.get("kind") or "").casefold() != "author-avatar"
        )
        messages.append(replace(message, assets=assets))
    return replace(conversation, messages=tuple(messages))


def _participant_has_identity(record: dict) -> bool:
    """Return whether a participant record has a usable human or stable identity."""
    return any(
        str(record.get(key) or "").strip()
        for key in ("id", "username", "display_name", "name")
    )


def _participant_records(conversation) -> tuple[dict, ...]:
    """Return identifiable DM participants with the current user's richer identity merged in."""
    metadata = dict(conversation.metadata)
    records: list[dict] = []
    by_id: dict[str, dict] = {}

    participants = metadata.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            record = dict(participant)
            participant_id = str(record.get("id") or "").strip()
            if participant_id:
                by_id[participant_id] = record
            records.append(record)

    current = metadata.get("current_user")
    if isinstance(current, dict):
        current_id = str(current.get("id") or "").strip()
        if current_id:
            target = by_id.get(current_id)
            if target is None:
                target = {"id": current_id, "is_self": True}
                records.append(target)
                by_id[current_id] = target
            target.update({key: value for key, value in current.items() if value is not None})
            target["is_self"] = True

    records = [record for record in records if _participant_has_identity(record)]

    title = str(conversation.title or "").strip()
    fallback_peer_username = title[1:].strip() if title.startswith("@") else ""
    if fallback_peer_username and " " not in fallback_peer_username:
        for record in records:
            if record.get("is_self") is True or str(record.get("username") or "").strip():
                continue
            record["username"] = fallback_peer_username
            break

    return tuple(sorted(records, key=lambda item: 0 if item.get("is_self") is True else 1))


def _participant_label(record: dict) -> str:
    """Prefer the human display name; fall back to username, then stable ID."""
    display_name = str(record.get("display_name") or record.get("name") or "").strip()
    username = str(record.get("username") or "").strip()
    participant_id = str(record.get("id") or "").strip()

    if display_name:
        return display_name
    if username:
        return username if username.startswith("@") else f"@{username}"
    return participant_id or "Unknown participant"


def _markdown_alt(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _prepend_dm_participant_header(
    markdown_path: Path,
    conversation,
    source_paths: dict[str, Path],
) -> None:
    """Prepend one inline identity header; message groups then use names only."""
    tokens: list[str] = []
    for record in _participant_records(conversation):
        label = _participant_label(record)
        avatar_url = str(record.get("avatar_url") or "").strip()
        local = source_paths.get(avatar_url) if avatar_url else None
        if local is not None:
            target = os.path.relpath(local, start=markdown_path.parent).replace(os.sep, "/")
        else:
            target = avatar_url or "missing-participant-avatar"
        alt = _markdown_alt(f"{_PARTICIPANT_AVATAR_PREFIX}{label}")
        tokens.append(f"![{alt}]({target})")

    if not tokens or not markdown_path.is_file():
        return
    body = markdown_path.read_text(encoding="utf-8")
    header = " ".join(tokens) + "\n\n---\n\n"
    markdown_path.write_text(header + body, encoding="utf-8", newline="")


def archive_collector_export(
    source_path: Path,
    *,
    archive_root: Path | None = None,
    progress: ProgressCallback | None = None,
) -> DiscordArchiveResult:
    """Normalize and archive one Discord collector JSON."""

    source_path = Path(source_path).expanduser().resolve()
    root = Path(archive_root or default_archive_root()).expanduser().resolve()
    downloads_dir = root / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    _emit(progress, "Reading and normalizing Discord collector export…")
    provider = DiscordProvider()
    with materialize_raw_json(source_path) as provider_source:
        incoming = _enrich_dm(
            provider.normalize(provider_source),
            source_path=source_path,
        )
    channel_id = _channel_id(incoming.conversation_id)
    raw_path, canonical_path, base_docx_path = discord_artifact_paths(
        root,
        incoming.metadata,
        channel_id,
    )
    database_path = root / "conversations-index.sqlite"
    asset_dir = root / "assets" / channel_id

    _emit(progress, "Locating existing cumulative archive…")
    legacy_docx, _legacy_raw, legacy_canonical = legacy_paths(root, channel_id)
    existing_path, existing = _find_existing_canonical(
        downloads_dir,
        channel_id,
        canonical_path,
        legacy_canonical,
    )
    _emit(progress, "Merging incoming messages with cumulative history…")
    conversation, updated = merge_dm_history(existing, incoming)
    _emit(progress, f"Cumulative conversation contains {len(conversation.messages)} message(s).")

    parts = plan_docx_parts(conversation)
    docx_paths = docx_paths_for_parts(base_docx_path, parts)
    docx_path = docx_paths[-1] if docx_paths else base_docx_path
    if len(parts) > 1:
        _emit(
            progress,
            "DOCX split plan: "
            + ", ".join(f"{part.label} ({part.message_count})" for part in parts),
        )

    _emit(progress, "Writing latest raw collector snapshot…")
    write_raw_archive(source_path, raw_path)

    available_assets = 0
    downloaded_assets = 0
    reused_assets = 0
    failed_assets: tuple[str, ...] = ()

    canonical_needs_write = updated or existing_path != canonical_path or not canonical_path.exists()
    if canonical_needs_write:
        _emit(progress, "Writing canonical conversation archive…")
        write_canonical_conversation(canonical_path, conversation)
    else:
        _emit(progress, "Canonical conversation is unchanged; keeping existing archive.")

    missing_docx = any(not path.is_file() or path.stat().st_size == 0 for path in docx_paths)
    if updated or missing_docx:
        _emit(progress, "Downloading/reusing Discord assets…")
        asset_result = download_conversation_assets(conversation, asset_dir)
        available_assets = asset_result.available
        downloaded_assets = asset_result.downloaded
        reused_assets = asset_result.reused
        failed_assets = asset_result.failed
        _emit(
            progress,
            "Assets ready: "
            f"{available_assets} available, {downloaded_assets} downloaded, "
            f"{reused_assets} reused, {len(failed_assets)} failed.",
        )

        with tempfile.TemporaryDirectory(
            prefix=".discord-exporter-markdown-",
            dir=root,
        ) as temp_dir:
            markdown_dir = Path(temp_dir)
            total_parts = len(parts)
            for index, (part, target_docx_path) in enumerate(zip(parts, docx_paths), start=1):
                prefix = f"[{index}/{total_parts}] " if total_parts > 1 else ""
                markdown_path = markdown_dir / f"{target_docx_path.stem}.md"
                _emit(
                    progress,
                    f"{prefix}Preparing {part.label} ({part.message_count} messages)…",
                )
                part_conversation = conversation_for_part(conversation, part)
                export_conversation = conversation_with_local_assets(
                    part_conversation,
                    asset_result.source_paths,
                    relative_to=markdown_dir,
                )
                export_conversation = _without_author_avatars(export_conversation)
                _emit(progress, f"{prefix}Rendering intermediate Markdown without per-message avatars…")
                export_canonical_markdown(
                    export_conversation,
                    markdown_path,
                    include_timestamps=True,
                    include_title=False,
                    chat_style=True,
                )
                _emit(progress, f"{prefix}Adding one participant identity/avatar header…")
                _prepend_dm_participant_header(
                    markdown_path,
                    part_conversation,
                    asset_result.source_paths,
                )
                _emit(progress, f"{prefix}Generating DOCX and embedding images…")
                export_docx(
                    markdown_path,
                    target_docx_path,
                    document_title=None,
                    overwrite=True,
                    progress=progress,
                )
                try:
                    docx_size = target_docx_path.stat().st_size
                except OSError:
                    docx_size = 0
                _emit(
                    progress,
                    f"{prefix}DOCX generated: {target_docx_path.name} ({docx_size} bytes).",
                )
    else:
        _emit(progress, "DOCX parts are already current; skipping regeneration.")
        if len(docx_paths) == 1:
            prior_docx = _find_prior_artifact(root, channel_id, ".docx", legacy_docx)
            if prior_docx and prior_docx != docx_path and not docx_path.exists():
                prior_docx.replace(docx_path)

    _emit(progress, "Cleaning stale Discord artifacts…")
    keep = {raw_path, canonical_path, *docx_paths}
    _remove_stale_artifacts(
        root,
        channel_id,
        keep=keep,
    )

    _emit(progress, "Updating search index…")
    update_index(
        root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        progress=progress,
    )
    _emit(progress, "Search index update complete.")

    _emit(progress, "Recording DOCX path in the index…")
    _record_docx_path(database_path, conversation.conversation_id, docx_path)
    _emit(progress, "Discord archive pipeline complete.")

    return DiscordArchiveResult(
        archive_root=root,
        raw_path=raw_path,
        canonical_path=canonical_path,
        docx_path=docx_path,
        database_path=database_path,
        message_count=len(conversation.messages),
        updated=updated,
        available_assets=available_assets,
        downloaded_assets=downloaded_assets,
        reused_assets=reused_assets,
        failed_assets=failed_assets,
        docx_paths=docx_paths,
    )
