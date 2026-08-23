"""Application identity and version metadata for GPT Exporter."""

from __future__ import annotations


APP_NAME = "GPT Exporter"
__version__ = "2.9.0.dev0"
LICENSE_ID = "GPL-3.0-or-later"
REPOSITORY_URL = "https://github.com/kerouanton/gpt-exporter"


def display_version(version: str = __version__) -> str:
    """Return a compact human-facing version label."""

    if version.endswith(".dev0"):
        return f"{version.removesuffix('.dev0')}-dev"
    return version


__all__ = [
    "APP_NAME",
    "LICENSE_ID",
    "REPOSITORY_URL",
    "__version__",
    "display_version",
]
