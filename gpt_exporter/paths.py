"""Path model for a GPT Exporter archive.

This module centralizes archive path construction without changing the v2.8
Windows defaults.  It deliberately performs no filesystem I/O at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


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
    """Return the v2.8 user-profile path with the same fallback semantics."""
    environment = os.environ if environ is None else environ
    configured = environment.get("USERPROFILE")
    if configured:
        return Path(configured)
    return Path.home() if home is None else Path(home)


def default_archive_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> ArchivePaths:
    """Return canonical paths for the unchanged v2.8 default archive root."""
    profile = default_user_profile(environ, home=home)
    return ArchivePaths.from_root(profile / "Documents" / "ChatGPT Archive")
