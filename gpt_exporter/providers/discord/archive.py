"""Provider-owned archive workflow for Discord collector exports."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gpt_exporter.core import read_canonical_conversation, write_canonical_conversation
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown
from gpt_exporter.index import update_index

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


def default_archive_root() -> Path:
    return Path.home() / "Documents" / "Discord Archive"


def _channel_id(conversation_id: str) -> str:
    prefix = "discord:"
    return conversation_id[len(prefix):] if conversation_id.startswith(prefix) else conversation_id


def archive_collector_export(
    source_path: Path,
    *,
    archive_root: Path | None = None,
) -> DiscordArchiveResult:
    """Normalize and archive one full-DM browser collector JSON.

    The source JSON is copied byte-for-byte into ``raw``.  Canonical JSON/XZ,
    Markdown/DOCX and SQLite are derived artifacts.  A partial collector run may
    not replace an archive containing message IDs that are absent from the new
    export.
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
    raw_path = raw_dir / f"discord_dm_{channel_id}.json"
    canonical_path = downloads_dir / f"discord_dm_{channel_id}.json.xz"
    docx_path = root / f"Discord DM {channel_id}.docx"
    database_path = root / "conversations-index.sqlite"

    updated = True
    if canonical_path.is_file() and canonical_path.stat().st_size > 0:
        existing = read_canonical_conversation(canonical_path)
        existing_ids = {message.message_id for message in existing.messages}
        incoming_ids = {message.message_id for message in conversation.messages}
        if not existing_ids.issubset(incoming_ids):
            conversation = existing
            updated = False

    if updated:
        shutil.copyfile(source_path, raw_path)
        write_canonical_conversation(canonical_path, conversation)

        with tempfile.TemporaryDirectory(prefix="discord-exporter-markdown-") as temp_dir:
            markdown_path = Path(temp_dir) / f"discord_dm_{channel_id}.md"
            export_canonical_markdown(
                conversation,
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

    return DiscordArchiveResult(
        archive_root=root,
        raw_path=raw_path,
        canonical_path=canonical_path,
        docx_path=docx_path,
        database_path=database_path,
        message_count=len(conversation.messages),
        updated=updated,
    )
