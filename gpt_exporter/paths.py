"""Path model for an exporter archive.

This module centralizes archive path construction. The filesystem layout is a
core invariant shared by every provider; only the default archive directory
name is source-specific.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DEFAULT_ARCHIVE_DIRECTORY_NAME = "ChatGPT Archive"


@dataclass(frozen=True, slots=True)
class ArchivePaths:
    """All canonical paths derived from one archive root."""

    root: Path
    downloads: Path
    assets: Path
    reports: Path
    markdown: Path
    database: Path

    @classmethod
    def from_root(cls, root: Path | str) -> "ArchivePaths":
        """Build canonical archive paths from an explicit root directory."""
        root_path = Path(root)
        return cls(
            root=root_path,
            downloads=root_path / "downloads",
            assets=root_path / "assets",
            reports=root_path / "reports",
            markdown=root_path / "markdown",
            database=root_path / "conversations-index.sqlite",
        )


def default_user_profile(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> Path:
    """Return the user-profile path with the existing Windows fallback semantics."""
    environment = os.environ if environ is None else environ
    configured = environment.get("USERPROFILE")
    if configured:
        return Path(configured)
    return Path.home() if home is None else Path(home)


def default_archive_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
    archive_directory_name: str = DEFAULT_ARCHIVE_DIRECTORY_NAME,
) -> ArchivePaths:
    """Return canonical paths for a provider's default archive root.

    ``archive_directory_name`` is the only provider-specific part of the
    default path. The layout below that root is deliberately identical for all
    current and future exporters.
    """
    directory_name = str(archive_directory_name).strip()
    if not directory_name:
        raise ValueError("Archive directory name cannot be empty.")
    profile = default_user_profile(environ, home=home)
    return ArchivePaths.from_root(profile / "Documents" / directory_name)


__all__ = [
    "ArchivePaths",
    "DEFAULT_ARCHIVE_DIRECTORY_NAME",
    "default_archive_paths",
    "default_user_profile",
]
