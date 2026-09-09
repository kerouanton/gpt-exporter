"""Provider-owned archive workflow for Discord collector exports."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
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
from .naming import dm_artifact_stem, dm_title, legacy_paths
from .provider import DiscordProvider


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
        payload = json.loads(Path(source_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
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
    return tuple(sorted(directory.glob(f"Discord DM * {channel_id}{suffix}")))


def _find_existing_canonical(downloads_dir: Path, channel_id: str, preferred: Path, legacy: Path):
    candidates: list[Path] = []
    for path in (preferred, legacy, *_human_named_paths(downloads_dir, channel_id, ".json.xz")):
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
    candidates.extend(_human_named_paths(root, channel_id, ".docx"))
    candidates.extend(_human_named_paths(root / "raw", channel_id, ".json"))
    candidates.extend(_human_named_paths(root / "downloads", channel_id, ".json.xz"))
    keep_resolved = {path.resolve() for path in keep}
    for path in candidates:
        try:
            if path.resolve() not in keep_resolved:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def archive_collector_export(
    source_path: Path,
    *,
    archive_root: Path | None = None,
) -> DiscordArchiveResult:
    """Normalize and archive one full-DM browser collector JSON."""

    source_path = Path(source_path).expanduser().resolve()
    root = Path(archive_root or default_archive_root()).expanduser().resolve()
    raw_dir = root / "raw"
    downloads_dir = root / "downloads"
    raw_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    provider = DiscordProvider()
    conversation = _enrich_dm(provider.normalize(source_path), source_path=source_path)
    channel_id = _channel_id(conversation.conversation_id)
    stem = dm_artifact_stem(conversation.metadata, channel_id)
    raw_path = raw_dir / f"{stem}.json"
    canonical_path = downloads_dir / f"{stem}.json.xz"
    docx_path = root / f"{stem}.docx"
    database_path = root / "conversations-index.sqlite"
    asset_dir = root / "assets" / channel_id

    legacy_docx, legacy_raw, legacy_canonical = legacy_paths(root, channel_id)
    existing_path, existing = _find_existing_canonical(
        downloads_dir,
        channel_id,
        canonical_path,
        legacy_canonical,
    )

    updated = True
    if existing is not None:
        existing_ids = {message.message_id for message in existing.messages}
        incoming_ids = {message.message_id for message in conversation.messages}
        if not existing_ids.issubset(incoming_ids):
            conversation = existing
            updated = False

    available_assets = 0
    downloaded_assets = 0
    reused_assets = 0
    failed_assets: tuple[str, ...] = ()

    if updated:
        if not raw_path.exists() or not source_path.samefile(raw_path):
            shutil.copyfile(source_path, raw_path)
        write_canonical_conversation(canonical_path, conversation)

        asset_result = download_conversation_assets(conversation, asset_dir)
        available_assets = asset_result.available
        downloaded_assets = asset_result.downloaded
        reused_assets = asset_result.reused
        failed_assets = asset_result.failed

        with tempfile.TemporaryDirectory(
            prefix=".discord-exporter-markdown-",
            dir=root,
        ) as temp_dir:
            markdown_dir = Path(temp_dir)
            markdown_path = markdown_dir / f"{stem}.md"
            export_conversation = conversation_with_local_assets(
                conversation,
                asset_result.source_paths,
                relative_to=markdown_dir,
            )
            export_canonical_markdown(
                export_conversation,
                markdown_path,
                include_timestamps=True,
                include_title=False,
                chat_style=True,
            )
            export_docx(
                markdown_path,
                docx_path,
                document_title=conversation.title,
                overwrite=True,
            )
    else:
        if existing_path != canonical_path:
            write_canonical_conversation(canonical_path, conversation)
        prior_docx = _find_prior_artifact(root, channel_id, ".docx", legacy_docx)
        if prior_docx and prior_docx != docx_path and not docx_path.exists():
            prior_docx.replace(docx_path)
        prior_raw = _find_prior_artifact(raw_dir, channel_id, ".json", legacy_raw)
        if prior_raw and prior_raw != raw_path and not raw_path.exists():
            shutil.copyfile(prior_raw, raw_path)

    _remove_stale_artifacts(
        root,
        channel_id,
        keep={source_path, raw_path, canonical_path, docx_path},
    )

    update_index(
        root,
        downloads_dir=downloads_dir,
        database_path=database_path,
    )
    _record_docx_path(database_path, conversation.conversation_id, docx_path)

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
    )
