"""ChatGPT-native indexing adapter for the provider-neutral index engine."""

from __future__ import annotations

import contextlib
import io
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from gpt_exporter.index.engine import (
    IndexUpdateResult,
    rebuild_index as rebuild_generic_index,
    update_index as update_generic_index,
)


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        from . import _native_indexer
    return _native_indexer


def index_native_conversation(connection, json_path: Path, archive_root: Path, *, force: bool = False) -> bool:
    """Index one native ChatGPT conversation using the retained v4 implementation."""
    return _implementation().index_one(
        connection,
        Path(json_path),
        Path(archive_root),
        force=force,
    )


def update_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    force: bool = False,
    progress=None,
) -> IndexUpdateResult:
    return update_generic_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        force=force,
        progress=progress,
        native_indexer=index_native_conversation,
    )


def rebuild_index(
    archive_root: Path | str,
    *,
    downloads_dir: Path | str | None = None,
    database_path: Path | str | None = None,
    progress=None,
) -> IndexUpdateResult:
    return rebuild_generic_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        progress=progress,
        native_indexer=index_native_conversation,
    )


__all__ = ["IndexUpdateResult", "index_native_conversation", "rebuild_index", "update_index"]
