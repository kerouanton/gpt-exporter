"""Provider-owned archive workflow for Discord collector exports."""

from __future__ import annotations

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


def _enrich_dm(conversation):
    """Add human title/origin and reusable author-avatar assets to a DM."""
    metadata = dict(conversation.metadata)
    channel_id = _channel_id(conversation.conversation_id)
    metadata["origin_type"] = "Direct Messages"
    metadata["origin_id"] = channel_id

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
        messages.append(replace(message, assets=assets))

    return replace(
        conversation,
        title=dm_title(metadata, conversation.title),
        messages=tuple(messages),
        metadata=metadata,
    )


def _record_docx_path(database_path: Path, conversation_id: str, docx_path: Path) -> None:
    """Persist the provider-derived DOCX location after generic indexing."""
    if not docx_path.is_file() or docx_path.stat().st_size == 0:
        return
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute(
            "UPDATE conversations SET docx_path = ? WHERE conversation_id = ?",
            (str(docx_path), conversation_id),
        )
        connection.commit()


def _remove_legacy_artifacts(root: Path, channel_id: str, *, keep_source: Path) -> None:
    for legacy in legacy_paths(root, channel_id):
        try:
            if legacy.resolve() != keep_source.resolve():
                legacy.unlink(missing_ok=True)
        except OSError:
            pass


def archive_collector_export(
    source_path: Path,
    *,
    archive_root: Path | None = None,
) -> DiscordArchiveResult:
    """Normalize and archive one full-DM browser collector JSON.

    The source JSON is copied byte-for-byte into ``raw``. Canonical JSON/XZ,
    local assets, DOCX and SQLite are derived artifacts. Discord media is
    acquired immediately while signed CDN URLs are valid. A partial collector
    run may not replace an archive containing message IDs that are absent from
    the new export.
    """

    source_path = Path(source_path).expanduser().resolve()
    root = Path(archive_root or default_archive_root()).expanduser().resolve()
    raw_dir = root / "raw"
    downloads_dir = root / "downloads"
    raw_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    provider = DiscordProvider()
    conversation = _enrich_dm(provider.normalize(source_path))
    channel_id = _channel_id(conversation.conversation_id)
    stem = dm_artifact_stem(conversation.metadata, channel_id)
    raw_path = raw_dir / f"{stem}.json"
    canonical_path = downloads_dir / f"{stem}.json.xz"
    docx_path = root / f"{stem}.docx"
    database_path = root / "conversations-index.sqlite"
    asset_dir = root / "assets" / channel_id

    legacy_docx, legacy_raw, legacy_canonical = legacy_paths(root, channel_id)
    existing_canonical = canonical_path if canonical_path.is_file() else legacy_canonical

    updated = True
    if existing_canonical.is_file() and existing_canonical.stat().st_size > 0:
        existing = _enrich_dm(read_canonical_conversation(existing_canonical))
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
            )
            export_docx(
                markdown_path,
                docx_path,
                document_title=conversation.title,
                overwrite=True,
            )
    else:
        if existing_canonical != canonical_path:
            write_canonical_conversation(canonical_path, conversation)
        if legacy_docx.is_file() and not docx_path.exists():
            legacy_docx.replace(docx_path)
        if legacy_raw.is_file() and not raw_path.exists():
            shutil.copyfile(legacy_raw, raw_path)

    _remove_legacy_artifacts(root, channel_id, keep_source=source_path)

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
