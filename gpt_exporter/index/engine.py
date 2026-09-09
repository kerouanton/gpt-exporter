"""Provider-neutral in-process archive indexing engine."""

from __future__ import annotations

import json
import logging
import lzma
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gpt_exporter.core.serialization import try_read_canonical_conversation
from gpt_exporter.index.canonical import index_canonical_conversation
from gpt_exporter.index.storage import connect_database, remove_database_files


ProgressCallback = Callable[[str], None]
NativeIndexer = Callable[..., bool]
LOGGER = logging.getLogger("gpt_exporter.index")


@dataclass(frozen=True, slots=True)
class IndexFailure:
    source_path: Path
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class IndexUpdateResult:
    archive_root: Path
    downloads_dir: Path
    database_path: Path
    total_files: int
    updated: int
    unchanged_or_skipped: int
    failures: tuple[IndexFailure, ...]
    force: bool

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def success(self) -> bool:
        return not self.failures


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _source_key(path: Path | str) -> str:
    """Return a stable local-filesystem key for an indexed source path."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _indexed_source_mtimes(connection: sqlite3.Connection) -> dict[str, int]:
    """Load the cheap source-path/mtime cache used before JSON decompression."""
    rows = connection.execute(
        "SELECT source_json_path, source_mtime_ns FROM conversations"
    ).fetchall()
    return {
        _source_key(row["source_json_path"]): int(row["source_mtime_ns"])
        for row in rows
        if row["source_json_path"]
    }


def _index_source(
    connection: sqlite3.Connection,
    json_path: Path,
    archive_root: Path,
    *,
    force: bool,
    native_indexer: NativeIndexer | None,
    progress: ProgressCallback | None = None,
) -> bool:
    canonical = try_read_canonical_conversation(json_path)
    if canonical is not None:
        return index_canonical_conversation(
            connection,
            canonical,
            source_path=json_path,
            archive_root=archive_root,
            force=force,
            progress=progress,
        )
    if native_indexer is None:
        raise ValueError(
            "Source is not a canonical conversation and no provider-native indexer was supplied"
        )
    return native_indexer(
        connection,
        json_path,
        archive_root,
        force=force,
    )


def update_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
    native_indexer: NativeIndexer | None = None,
) -> IndexUpdateResult:
    """Index canonical sources plus optional provider-native sources."""
    archive_root = Path(archive_root).expanduser().resolve()
    resolved_downloads = (
        Path(downloads_dir).expanduser().resolve()
        if downloads_dir is not None
        else archive_root / "downloads"
    )
    resolved_database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else archive_root / "conversations-index.sqlite"
    )
    if not resolved_downloads.is_dir():
        raise FileNotFoundError(f"Downloads directory does not exist: {resolved_downloads}")

    resolved_database.parent.mkdir(parents=True, exist_ok=True)
    json_files = sorted(resolved_downloads.rglob("*.json.xz"))
    _emit(progress, f"Found {len(json_files)} compressed conversation JSON files")
    if not json_files:
        return IndexUpdateResult(
            archive_root, resolved_downloads, resolved_database, 0, 0, 0, (), force
        )

    updated = 0
    fast_skipped = 0
    failures: list[IndexFailure] = []
    connection = connect_database(resolved_database)
    try:
        indexed_mtimes = {} if force else _indexed_source_mtimes(connection)
        for file_number, json_path in enumerate(json_files, start=1):
            try:
                # The source path and nanosecond mtime are already stored in the
                # index. Check those cheap filesystem values before opening an XZ
                # stream. This keeps application startup proportional to directory
                # enumeration rather than to decompression/parsing of the archive.
                if not force:
                    source_mtime_ns = json_path.stat().st_mtime_ns
                    if indexed_mtimes.get(_source_key(json_path)) == source_mtime_ns:
                        fast_skipped += 1
                        continue

                _emit(
                    progress,
                    f"Indexing conversation source {file_number}/{len(json_files)}: {json_path.name}",
                )
                changed = _index_source(
                    connection,
                    json_path,
                    archive_root,
                    force=force,
                    native_indexer=native_indexer,
                    progress=progress,
                )
                if changed:
                    updated += 1
                    _emit(progress, f"Indexed: {json_path.name}")
            except (OSError, ValueError, json.JSONDecodeError, lzma.LZMAError) as error:
                failures.append(IndexFailure(json_path, type(error).__name__, str(error)))
                LOGGER.exception("Could not index %s: %s", json_path, error)
                _emit(progress, f"FAILED: {json_path.name}: {type(error).__name__}: {error}")
    finally:
        connection.close()

    unchanged = len(json_files) - updated - len(failures)
    result = IndexUpdateResult(
        archive_root,
        resolved_downloads,
        resolved_database,
        len(json_files),
        updated,
        unchanged,
        tuple(failures),
        force,
    )
    if fast_skipped:
        LOGGER.debug("Fast-skipped %d unchanged indexed sources", fast_skipped)
    _emit(
        progress,
        f"Index complete: {result.updated} updated, {result.unchanged_or_skipped} unchanged or skipped, {result.failed} failed",
    )
    _emit(progress, f"Database: {resolved_database}")
    return result


def rebuild_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    progress: ProgressCallback | None = None,
    native_indexer: NativeIndexer | None = None,
) -> IndexUpdateResult:
    """Delete the disposable index and rebuild it from source conversations."""
    archive_root = Path(archive_root).expanduser().resolve()
    resolved_database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else archive_root / "conversations-index.sqlite"
    )
    resolved_database.parent.mkdir(parents=True, exist_ok=True)
    remove_database_files(resolved_database)
    return update_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=resolved_database,
        force=True,
        progress=progress,
        native_indexer=native_indexer,
    )
