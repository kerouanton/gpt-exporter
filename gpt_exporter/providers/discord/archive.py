"""Provider-owned archive workflow for Discord collector exports."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path

from gpt_exporter.core.serialization import (
    read_canonical_conversation,
    write_canonical_conversation,
)
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown
from gpt_exporter.index import update_index

from .assets import conversation_with_local_assets, download_conversation_assets
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
    conversation = provider.normalize(source_path)
    channel_id = _channel_id(conversation.conversation_id)
    conversation = replace(
        conversation,
        metadata={
            **dict(conversation.metadata),
            "origin_type": "Direct Messages",
            "origin_id": channel_id,
        },
    )
    raw_path = raw_dir / f"discord_dm_{channel_id}.json"
    canonical_path = downloads_dir / f"discord_dm_{channel_id}.json.xz"
    docx_path = root / f"Discord DM {channel_id}.docx"
    database_path = root / "conversations-index.sqlite"
    asset_dir = root / "assets" / channel_id

    updated = True
    if canonical_path.is_file() and canonical_path.stat().st_size > 0:
        existing = read_canonical_conversation(canonical_path)
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

        # Keep the stored canonical source references provider-original. Only the
        # export view is rewritten to relative local paths so the generic DOCX
        # renderer can embed images and link other downloaded media.
        with tempfile.TemporaryDirectory(
            prefix=".discord-exporter-markdown-",
            dir=root,
        ) as temp_dir:
            markdown_dir = Path(temp_dir)
            markdown_path = markdown_dir / f"discord_dm_{channel_id}.md"
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
