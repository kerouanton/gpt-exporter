"""Path model for a GPT Exporter archive.

This module centralizes archive path construction without changing the v2.8
Windows defaults. It deliberately performs no filesystem I/O at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class LegacyArchivePaths:
    """Canonical storage paths for historical legacy-DOCX material."""

    root: Path
    sources: Path
    normalized_docx: Path
    reconstruction: Path
    turns: Path
    semantic_audit_json: Path
    semantic_audit_csv: Path

    @classmethod
    def from_archive_root(cls, archive_root: Path | str) -> "LegacyArchivePaths":
        """Build legacy paths below one ChatGPT Archive root."""
        root = Path(archive_root) / "legacy"
        reconstruction = root / "reconstruction"
        return cls(
            root=root,
            sources=root / "sources",
            normalized_docx=root / "normalized-docx",
            reconstruction=reconstruction,
            turns=reconstruction / "legacy-docx-turns.json",
            semantic_audit_json=reconstruction / "legacy-semantic-audit.json",
            semantic_audit_csv=reconstruction / "legacy-semantic-audit.csv",
        )


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

    @property
    def legacy(self) -> LegacyArchivePaths:
        """Return canonical legacy paths below this archive root."""
        return LegacyArchivePaths.from_archive_root(self.root)


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


def default_legacy_paths(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> LegacyArchivePaths:
    """Return canonical paths for legacy sources and derived reconstruction data."""
    return default_archive_paths(environ, home=home).legacy
