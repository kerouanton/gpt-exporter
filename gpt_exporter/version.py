"""Application identity and version metadata for GPT Exporter."""

from __future__ import annotations

import re


APP_NAME = "GPT Exporter"
__version__ = "2.9.0.dev0"
LICENSE_ID = "GPL-3.0-or-later"
REPOSITORY_URL = "https://github.com/kerouanton/gpt-exporter"


def display_version(version: str = __version__) -> str:
    """Return a compact human-facing version label."""

    if version.endswith(".dev0"):
        return f"{version.removesuffix('.dev0')}-dev"
    return version


def windows_version_tuple(version: str = __version__) -> tuple[int, int, int, int]:
    """Return the four-integer version required by a Windows PE resource."""

    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"Version does not start with major.minor.patch: {version}")
    return tuple(int(part) for part in match.groups()) + (0,)


__all__ = [
    "APP_NAME",
    "LICENSE_ID",
    "REPOSITORY_URL",
    "__version__",
    "display_version",
    "windows_version_tuple",
]
