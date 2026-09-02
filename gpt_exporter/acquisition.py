"""Provider-neutral browser acquisition helpers.

The exporter core owns the mechanics for locating a freshly downloaded source
bundle, reporting collection instructions, and deleting a consumed bundle after
successful processing. Providers supply only their identity, website, collector
resource, and expected bundle filename.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from gpt_exporter.providers import ExporterProvider
from gpt_exporter.providers.base import ProgressCallback


def _emit(progress: ProgressCallback | None, message: str = "") -> None:
    if progress is not None:
        progress(message)


def windows_download_directories(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> list[Path]:
    """Return unique Windows Downloads candidates in deterministic order."""

    environment = os.environ if environ is None else environ
    candidates: list[Path] = []

    user_profile = environment.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Downloads")

    home_drive = environment.get("HOMEDRIVE")
    home_path = environment.get("HOMEPATH")
    if home_drive and home_path:
        candidates.append(Path(f"{home_drive}{home_path}") / "Downloads")

    candidates.append((Path.home() if home is None else Path(home)) / "Downloads")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def source_bundle_signature(path: Path | str | None) -> tuple[str, int, int] | None:
    """Return a stable signature for detecting a newly downloaded bundle."""

    if path is None:
        return None
    candidate = Path(path)
    try:
        stat = candidate.stat()
    except OSError:
        return None
    return (
        os.path.normcase(os.path.abspath(str(candidate))),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def find_source_bundle(
    provider: ExporterProvider,
    *,
    download_directories: list[Path] | None = None,
    progress: ProgressCallback | None = None,
) -> Path | None:
    """Return the newest non-empty source bundle for ``provider``."""

    directories = download_directories or windows_download_directories()
    matches: list[Path] = []

    for directory in directories:
        candidate = Path(directory) / provider.source_bundle_name
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                matches.append(candidate)
        except OSError:
            continue

    if not matches:
        return None

    source = max(matches, key=lambda path: path.stat().st_mtime)
    _emit(progress)
    _emit(progress, f"Found {provider.display_name} source bundle in Downloads: {source}")
    _emit(progress, "The bundle will be processed in place and deleted after a successful run.")
    return source


def bundle_creation_instructions(provider: ExporterProvider) -> tuple[str, ...]:
    """Return provider-aware browser collection instructions."""

    return (
        f"To generate {provider.source_bundle_name}:",
        f"  1. Open your web browser and go to {provider.website_url}",
        "  2. Press F12 to open Developer Tools.",
        "  3. Open the Console tab.",
        f"  4. Copy the complete contents of {provider.collector_name}.",
        "  5. Paste the script into the console and run it.",
        f"  6. Leave the downloaded {provider.source_bundle_name} in Windows Downloads,",
        "     then start the archive workflow again. It will process the file in place.",
    )


def print_bundle_creation_instructions(
    provider: ExporterProvider,
    progress: ProgressCallback | None,
) -> None:
    """Emit provider-aware collection instructions through ``progress``."""

    _emit(progress)
    for line in bundle_creation_instructions(provider):
        _emit(progress, line)


def require_source_bundle(
    provider: ExporterProvider,
    *,
    download_directories: list[Path] | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    """Find a source bundle or raise with provider-specific guidance."""

    directories = download_directories or windows_download_directories()
    path = find_source_bundle(
        provider,
        download_directories=directories,
        progress=progress,
    )
    if path is not None:
        return path

    print_bundle_creation_instructions(provider, progress)
    searched = ", ".join(str(path) for path in directories)
    raise FileNotFoundError(
        f"Required file is missing or empty: {provider.source_bundle_name}. "
        f"Searched Windows Downloads locations: {searched}"
    )


def delete_consumed_source_bundle(
    path: Path,
    *,
    progress: ProgressCallback | None = None,
) -> bool:
    """Delete a consumed source bundle, warning rather than failing on error."""

    try:
        Path(path).unlink()
    except OSError as exc:
        _emit(progress)
        _emit(progress, f"WARNING: archive succeeded, but the source bundle could not be deleted: {path}")
        _emit(progress, f"WARNING: {exc}")
        return False

    _emit(progress)
    _emit(progress, f"Deleted consumed browser bundle: {path}")
    return True


__all__ = [
    "bundle_creation_instructions",
    "delete_consumed_source_bundle",
    "find_source_bundle",
    "print_bundle_creation_instructions",
    "require_source_bundle",
    "source_bundle_signature",
    "windows_download_directories",
]
