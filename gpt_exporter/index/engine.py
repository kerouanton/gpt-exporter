"""In-process archive indexing API.

The adapter supports both historical ChatGPT JSON/XZ exports and the
provider-neutral canonical conversation schema. Concrete provider parsing stays
outside the core index path; canonical inputs are indexed directly.
"""

from __future__ import annotations

import contextlib
import io
import json
import lzma
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Callable

from gpt_exporter.core.serialization import try_read_canonical_conversation
from gpt_exporter.index.canonical import index_canonical_conversation


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class IndexFailure:
    """One source conversation that could not be indexed."""

    source_path: Path
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class IndexUpdateResult:
    """Structured result of one incremental or forced index update."""

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


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    """Load the package-local historical ChatGPT indexer without diagnostics."""

    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        from . import _legacy_indexer
    return _legacy_indexer


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _index_source(
    connection,
    implementation: ModuleType,
    json_path: Path,
    archive_root: Path,
    *,
    force: bool,
) -> bool:
    canonical = try_read_canonical_conversation(json_path)
    if canonical is not None:
        return index_canonical_conversation(
            connection,
            canonical,
            source_path=json_path,
            archive_root=archive_root,
            force=force,
        )
    return implementation.index_one(
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
) -> IndexUpdateResult:
    """Create or incrementally update the archive SQLite index in-process."""

    implementation = _implementation()
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
        raise FileNotFoundError(
            f"Downloads directory does not exist: {resolved_downloads}"
        )

    resolved_database.parent.mkdir(parents=True, exist_ok=True)
    json_files = sorted(resolved_downloads.rglob("*.json.xz"))
    _emit(progress, f"Found {len(json_files)} compressed conversation JSON files")

    if not json_files:
        return IndexUpdateResult(
            archive_root=archive_root,
            downloads_dir=resolved_downloads,
            database_path=resolved_database,
            total_files=0,
            updated=0,
            unchanged_or_skipped=0,
            failures=(),
            force=force,
        )

    updated = 0
    failures: list[IndexFailure] = []

    connection = implementation.connect_database(resolved_database)
    try:
        for json_path in json_files:
            try:
                changed = _index_source(
                    connection,
                    implementation,
                    json_path,
                    archive_root,
                    force=force,
                )
                if changed:
                    updated += 1
                    _emit(progress, f"Indexed: {json_path.name}")
            except (
                OSError,
                ValueError,
                json.JSONDecodeError,
                lzma.LZMAError,
            ) as error:
                failures.append(
                    IndexFailure(
                        source_path=json_path,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                implementation.LOGGER.exception(
                    "Could not index %s: %s",
                    json_path,
                    error,
                )
                _emit(
                    progress,
                    f"FAILED: {json_path.name}: {type(error).__name__}: {error}",
                )
    finally:
        connection.close()

    unchanged = len(json_files) - updated - len(failures)
    result = IndexUpdateResult(
        archive_root=archive_root,
        downloads_dir=resolved_downloads,
        database_path=resolved_database,
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
    _emit(progress, f"Database: {resolved_database}")
    return result


def rebuild_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> IndexUpdateResult:
    """Delete the disposable SQLite index and rebuild it from source JSON/XZ."""

    implementation = _implementation()
    archive_root = Path(archive_root).expanduser().resolve()
    resolved_database = (
        Path(database_path).expanduser().resolve()
        if database_path is not None
        else archive_root / "conversations-index.sqlite"
    )
    resolved_database.parent.mkdir(parents=True, exist_ok=True)
    implementation.remove_database_files(resolved_database)
    return update_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=resolved_database,
        force=True,
        progress=progress,
    )
