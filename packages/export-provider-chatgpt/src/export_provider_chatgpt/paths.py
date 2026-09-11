"""Default filesystem locations owned by the ChatGPT provider."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from gpt_exporter.paths import ArchivePaths, default_user_profile


DEFAULT_ARCHIVE_DIRECTORY_NAME = "ChatGPT Archive"


def default_archive_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> ArchivePaths:
    """Return the historical GPT Exporter v2.8 default archive paths."""
    profile = default_user_profile(environ, home=home)
    return ArchivePaths.from_root(
        profile / "Documents" / DEFAULT_ARCHIVE_DIRECTORY_NAME
    )


__all__ = ["DEFAULT_ARCHIVE_DIRECTORY_NAME", "default_archive_paths"]
