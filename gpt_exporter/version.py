"""Application identity and version metadata.

The product is being migrated from the historical GPT Exporter identity to
Multi Social Network Explorer (MSNE). Keep user-facing, distribution, import,
repository, and packaging identities explicit so each compatibility surface
can move on its own schedule instead of through a repository-wide search/replace.
"""

from __future__ import annotations

import re


# Historical identity. These values are compatibility surfaces and must not be
# changed implicitly when the visible product name moves to MSNE.
LEGACY_APP_NAME = "GPT Exporter"
LEGACY_DISTRIBUTION_NAME = "gpt-exporter"
LEGACY_PYTHON_PACKAGE = "gpt_exporter"
LEGACY_REPOSITORY_NAME = "gpt-exporter"

# Canonical product identity. Packaging/import/repository compatibility may
# continue to use the explicit legacy constants during the migration.
TARGET_APP_NAME = "Multi Social Network Explorer"
APP_NAME = TARGET_APP_NAME
APP_SHORT_NAME = "MSNE"

# Windows packaging identities are migrated independently. MSNE.exe is the
# canonical executable, while GPT Exporter.exe remains a compatibility alias
# inside the historical onedir folder during this phase.
WINDOWS_CANONICAL_BASENAME = APP_SHORT_NAME
WINDOWS_LEGACY_BASENAME = LEGACY_APP_NAME
WINDOWS_ONEDIR_NAME = LEGACY_APP_NAME

__version__ = "2.9.0"
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
    "APP_SHORT_NAME",
    "LEGACY_APP_NAME",
    "LEGACY_DISTRIBUTION_NAME",
    "LEGACY_PYTHON_PACKAGE",
    "LEGACY_REPOSITORY_NAME",
    "LICENSE_ID",
    "REPOSITORY_URL",
    "TARGET_APP_NAME",
    "WINDOWS_CANONICAL_BASENAME",
    "WINDOWS_LEGACY_BASENAME",
    "WINDOWS_ONEDIR_NAME",
    "__version__",
    "display_version",
    "windows_version_tuple",
]
