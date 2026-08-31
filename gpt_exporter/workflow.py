"""Provider-aware workflow helpers shared by CLI and GUI layers.

This module contains no Tk widgets. It binds generic acquisition and provider
contracts into a small workflow API and delegates archive execution to the
provider-aware pipeline bridge.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path

from gpt_exporter.acquisition import find_source_bundle, require_source_bundle
from gpt_exporter.pipeline import ArchivePipelineResult
from gpt_exporter.provider_pipeline import archive_provider_bundle
from gpt_exporter.providers import CHATGPT_PROVIDER, ExporterProvider
from gpt_exporter.providers.base import ProgressCallback


# Compatibility seam for tests/extensions that patch the workflow backend.
archive_bundle = archive_provider_bundle


@dataclass(frozen=True, slots=True)
class ProviderWorkflow:
    """Bind one provider to generic acquisition and archive operations."""

    provider: ExporterProvider

    def open_website(self) -> bool:
        """Open the provider website in the default browser."""
        return bool(webbrowser.open(self.provider.website_url, new=2))

    def read_collector_source(self) -> str:
        """Return the provider collector source exactly as packaged."""
        return self.provider.read_collector_source()

    def find_source_bundle(
        self,
        *,
        download_directories: list[Path] | None = None,
        progress: ProgressCallback | None = None,
    ) -> Path | None:
        return find_source_bundle(
            self.provider,
            download_directories=download_directories,
            progress=progress,
        )

    def require_source_bundle(
        self,
        *,
        download_directories: list[Path] | None = None,
        progress: ProgressCallback | None = None,
    ) -> Path:
        return require_source_bundle(
            self.provider,
            download_directories=download_directories,
            progress=progress,
        )

    def run_archive(
        self,
        *,
        archive_root: Path | str | None = None,
        source_bundle: Path | str | None = None,
        convert_only: bool = False,
        fresh: bool = False,
        skip_assets: bool = False,
        legacy_root: Path | str | None = None,
        download_directories: list[Path] | None = None,
        delete_source: bool = True,
        progress: ProgressCallback | None = None,
    ) -> ArchivePipelineResult:
        """Run the archive workflow for this provider."""

        return archive_bundle(
            self.provider,
            archive_root=archive_root,
            source_bundle=source_bundle,
            convert_only=convert_only,
            fresh=fresh,
            skip_assets=skip_assets,
            legacy_root=legacy_root,
            download_directories=download_directories,
            delete_source=delete_source,
            progress=progress,
        )


CHATGPT_WORKFLOW = ProviderWorkflow(CHATGPT_PROVIDER)


__all__ = ["CHATGPT_WORKFLOW", "ProviderWorkflow"]
