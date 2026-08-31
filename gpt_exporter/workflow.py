"""Provider/workspace-aware workflow helpers shared by CLI and GUI layers.

This module contains no Tk widgets. It binds generic acquisition and provider
contracts into small workflow APIs and delegates archive execution to the
provider-aware pipeline bridge.
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path

from gpt_exporter.acquisition import find_source_bundle, require_source_bundle
from gpt_exporter.index import IndexUpdateResult, update_normalized_index
from gpt_exporter.pipeline import ArchivePipelineResult
from gpt_exporter.provider_pipeline import archive_provider_bundle
from gpt_exporter.providers import CHATGPT_PROVIDER, ExporterProvider
from gpt_exporter.providers.base import ProgressCallback
from gpt_exporter.workspaces import Workspace


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


@dataclass(frozen=True, slots=True)
class WorkspaceWorkflow:
    """One coherent operating context for a selected workspace.

    The workspace determines provider, archive root and production database.
    Callers no longer need to carry those independently, which prevents an
    action from accidentally targeting another workspace's archive.
    """

    workspace: Workspace

    @property
    def provider(self) -> ExporterProvider:
        return self.workspace.provider

    @property
    def provider_workflow(self) -> ProviderWorkflow:
        return ProviderWorkflow(self.provider)

    @property
    def archive_root(self) -> Path:
        return self.workspace.archive_root

    @property
    def paths(self):
        return self.workspace.paths

    @property
    def database_path(self) -> Path:
        return self.workspace.database_path

    def open_website(self) -> bool:
        return self.provider_workflow.open_website()

    def read_collector_source(self) -> str:
        return self.provider_workflow.read_collector_source()

    def find_source_bundle(
        self,
        *,
        download_directories: list[Path] | None = None,
        progress: ProgressCallback | None = None,
    ) -> Path | None:
        return self.provider_workflow.find_source_bundle(
            download_directories=download_directories,
            progress=progress,
        )

    def require_source_bundle(
        self,
        *,
        download_directories: list[Path] | None = None,
        progress: ProgressCallback | None = None,
    ) -> Path:
        return self.provider_workflow.require_source_bundle(
            download_directories=download_directories,
            progress=progress,
        )

    def update_index(
        self,
        *,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> IndexUpdateResult:
        """Update this workspace's production search index through CORE."""

        return update_normalized_index(
            self.provider,
            self.archive_root,
            downloads_dir=self.paths.downloads,
            database_path=self.database_path,
            force=force,
            progress=progress,
        )

    def run_archive(
        self,
        *,
        source_bundle: Path | str | None = None,
        convert_only: bool = False,
        fresh: bool = False,
        skip_assets: bool = False,
        legacy_root: Path | str | None = None,
        download_directories: list[Path] | None = None,
        delete_source: bool = True,
        progress: ProgressCallback | None = None,
    ) -> ArchivePipelineResult:
        return self.provider_workflow.run_archive(
            archive_root=self.archive_root,
            source_bundle=source_bundle,
            convert_only=convert_only,
            fresh=fresh,
            skip_assets=skip_assets,
            legacy_root=legacy_root,
            download_directories=download_directories,
            delete_source=delete_source,
            progress=progress,
        )


# Compatibility singleton retained for older callers while the application path
# migrates to WorkspaceWorkflow.
CHATGPT_WORKFLOW = ProviderWorkflow(CHATGPT_PROVIDER)


__all__ = ["CHATGPT_WORKFLOW", "ProviderWorkflow", "WorkspaceWorkflow"]
