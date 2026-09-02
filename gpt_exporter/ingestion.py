"""Provider-neutral source ingestion boundary.

This module is intentionally small: the core resolves archive paths and invokes
the importer supplied by a provider. Native parsing and preservation rules stay
inside that provider implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gpt_exporter.paths import ArchivePaths, default_archive_paths
from gpt_exporter.providers import ExporterProvider
from gpt_exporter.providers.base import ProgressCallback


@dataclass(frozen=True, slots=True)
class SourceIngestionResult:
    """One provider-native ingestion operation and its resolved archive paths."""

    provider_key: str
    source_bundle: Path
    paths: ArchivePaths
    provider_result: Any


def resolve_provider_archive_paths(
    provider: ExporterProvider,
    archive_root: Path | str | None = None,
) -> ArchivePaths:
    """Resolve the shared archive layout for one provider."""

    if archive_root is None:
        return default_archive_paths(
            archive_directory_name=provider.archive_directory_name,
        )
    root = Path(archive_root).expanduser().resolve()
    return ArchivePaths.from_root(root)


def ingest_source_bundle(
    provider: ExporterProvider,
    bundle_path: Path | str,
    *,
    archive_root: Path | str | None = None,
    progress: ProgressCallback | None = None,
) -> SourceIngestionResult:
    """Import one provider-native bundle through the provider contract."""

    source = Path(bundle_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source bundle not found: {source}")
    if source.stat().st_size <= 0:
        raise ValueError(f"Source bundle is empty: {source}")

    paths = resolve_provider_archive_paths(provider, archive_root)
    paths.root.mkdir(parents=True, exist_ok=True)

    provider_result = provider.importer(
        source,
        archive_root=paths.root,
        progress=progress,
    )

    return SourceIngestionResult(
        provider_key=provider.key,
        source_bundle=source,
        paths=paths,
        provider_result=provider_result,
    )


__all__ = [
    "SourceIngestionResult",
    "ingest_source_bundle",
    "resolve_provider_archive_paths",
]
