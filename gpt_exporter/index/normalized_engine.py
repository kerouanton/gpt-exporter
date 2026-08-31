"""Incremental provider-neutral archive indexing.

This mirrors the historical index update contract while obtaining each
conversation through the selected provider's normalizer.  The existing browser
schema and user organization tables remain authoritative and are preserved.
"""

from __future__ import annotations

import json
import lzma
from pathlib import Path
from typing import Callable

from gpt_exporter.providers.base import ExporterProvider

from .engine import IndexFailure, IndexUpdateResult
from .normalized import (
    index_normalized_conversation,
    initialize_normalized_database,
)
from . import _legacy_indexer as legacy


ProgressCallback = Callable[[str], None]


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def update_normalized_index(
    provider: ExporterProvider,
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> IndexUpdateResult:
    """Incrementally update the production index from normalized conversations.

    Observable update semantics intentionally match ``engine.update_index``:
    compressed conversation files are processed in sorted order, source mtime
    controls unchanged/skipped detection, per-conversation decoding failures are
    recorded and processing continues, and structural SQLite failures propagate.
    """

    archive = Path(archive_root).expanduser().resolve()
    downloads = (
        Path(downloads_dir).expanduser().resolve()
        if downloads_dir is not None
        else archive / "downloads"
    )
    database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else archive / "conversations-index.sqlite"
    )

    if not downloads.is_dir():
        raise FileNotFoundError(f"Downloads directory does not exist: {downloads}")

    initialize_normalized_database(database)
    json_files = sorted(downloads.rglob("*.json.xz"))
    _emit(progress, f"Found {len(json_files)} compressed conversation JSON files")

    if not json_files:
        return IndexUpdateResult(
            archive_root=archive,
            downloads_dir=downloads,
            database_path=database,
            total_files=0,
            updated=0,
            unchanged_or_skipped=0,
            failures=(),
            force=force,
        )

    updated = 0
    failures: list[IndexFailure] = []
    connection = legacy.connect_database(database)
    try:
        for source in json_files:
            try:
                source_mtime_ns = source.stat().st_mtime_ns
                conversation = provider.normalize_conversation(source)
                existing = connection.execute(
                    "SELECT source_mtime_ns FROM conversations WHERE conversation_id = ?",
                    (conversation.conversation_id,),
                ).fetchone()
                if (
                    not force
                    and existing
                    and existing["source_mtime_ns"] == source_mtime_ns
                ):
                    continue

                index_normalized_conversation(
                    connection,
                    conversation,
                    source_path=source,
                    archive_root=archive,
                    source_mtime_ns=source_mtime_ns,
                )
                updated += 1
                _emit(progress, f"Indexed: {source.name}")
            except (
                OSError,
                ValueError,
                json.JSONDecodeError,
                lzma.LZMAError,
            ) as error:
                failures.append(
                    IndexFailure(
                        source_path=source,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                _emit(
                    progress,
                    f"FAILED: {source.name}: {type(error).__name__}: {error}",
                )
    finally:
        connection.close()

    unchanged = len(json_files) - updated - len(failures)
    result = IndexUpdateResult(
        archive_root=archive,
        downloads_dir=downloads,
        database_path=database,
        total_files=len(json_files),
        updated=updated,
        unchanged_or_skipped=unchanged,
        failures=tuple(failures),
        force=force,
    )
    _emit(
        progress,
        "Index complete: "
        f"{result.updated} updated, "
        f"{result.unchanged_or_skipped} unchanged or skipped, "
        f"{result.failed} failed",
    )
    _emit(progress, f"Database: {database}")
    return result


__all__ = ["update_normalized_index"]
