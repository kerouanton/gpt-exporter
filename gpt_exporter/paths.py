"""Provider-neutral archive path model.

The shared engine derives all storage locations from an explicit archive root.
Historical provider defaults are exposed only through lazy compatibility helpers
so importing this module never loads a concrete provider.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ArchivePaths:
    """All provider-neutral canonical paths derived from one archive root."""

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
    """Return the historical user-profile path with the same fallback semantics."""
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
    """Compatibility helper for the historical GPT Exporter default.

    New provider-neutral code should use :meth:`ArchivePaths.from_root` with an
    explicit root. The extracted ChatGPT distribution is imported lazily so merely
    importing ``gpt_exporter.paths`` remains provider-independent.
    """
    from gpt_exporter.provider_loader import prepare_source_provider_imports

    prepare_source_provider_imports()
    from export_provider_chatgpt.paths import default_archive_paths as gpt_default

    return gpt_default(environ, home=home)


__all__ = ["ArchivePaths", "default_archive_paths", "default_user_profile"]
