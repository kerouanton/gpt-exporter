"""Provider-aware archive pipeline built on the preserved v2.8 mechanics.

This module is the migration bridge between the source-specific provider
contract and the common exporter core. It intentionally reuses the proven
archive migration, asset, and batch-export stages while routing source
acquisition/import and production indexing through ``ExporterProvider``.

ChatGPT remains the only provider whose native asset/incremental-export stages
are connected here. Other providers are rejected explicitly until their
provider-native preservation semantics are defined.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gpt_exporter.acquisition import delete_consumed_source_bundle, require_source_bundle
from gpt_exporter.archive.inventory import (
    InventoryResult,
    inventory_media,
    render_console_summary as render_inventory_summary,
)
from gpt_exporter.archive.manifest import (
    AssetManifestResult,
    build_asset_manifest,
    render_console_summary as render_manifest_summary,
)
from gpt_exporter.export.batch import BatchExportResult
from gpt_exporter.export.normalized_batch import export_normalized_batch
from gpt_exporter.index import IndexUpdateResult, update_normalized_index
from gpt_exporter.paths import ArchivePaths, default_archive_paths
from gpt_exporter.pipeline import (
    ArchivePipelineResult,
    _call_stage,
    _conversation_files,
    _emit,
    clear_generated_data,
    migrate_json_storage,
    migrate_legacy_archive,
    migrate_output_layout,
)
from gpt_exporter.providers import CHATGPT_PROVIDER, ExporterProvider
from gpt_exporter.providers.base import ProgressCallback
from gpt_exporter.validation import run_normalized_shadow_validation


def _resolved_paths(
    provider: ExporterProvider,
    archive_root: Path | str | None,
) -> ArchivePaths:
    if archive_root is None:
        return default_archive_paths(
            archive_directory_name=provider.archive_directory_name,
        )
    return ArchivePaths.from_root(Path(archive_root).expanduser().resolve())


def _resolve_validation_sources(
    paths: ArchivePaths,
    *,
    convert_only: bool,
    batch_data: dict[str, Any] | None,
) -> list[Path]:
    """Return preserved native files to exercise through the normalized path."""

    if convert_only:
        return _conversation_files(paths.downloads)

    names = (batch_data or {}).get("conversation_files") or []
    sources: list[Path] = []
    for raw_name in names:
        candidate = Path(str(raw_name))
        if not candidate.is_absolute():
            candidate = paths.downloads / candidate
        if candidate.is_file():
            sources.append(candidate)
    return sources


def archive_provider_bundle(
    provider: ExporterProvider,
    *,
    archive_root: Path | str | None = None,
    source_bundle: Path | str | None = None,
    convert_only: bool = False,
    fresh: bool = False,
    skip_assets: bool = False,
    legacy_root: Path | str | None = None,
    download_directories: list[Path] | None = None,
    delete_source: bool = True,
    validate_normalized: bool = True,
    progress: ProgressCallback | None = None,
) -> ArchivePipelineResult:
    """Run one provider archive while preserving current ChatGPT semantics.

    The source bundle is acquired and imported through ``provider``. The proven
    ChatGPT asset stages remain in place for now. Production export and indexing
    are provider-neutral and consume the normalized display/search projections.
    A separate legacy oracle still validates the normalized result.
    """

    if provider.key != CHATGPT_PROVIDER.key:
        raise NotImplementedError(
            f"Provider '{provider.key}' does not yet define compatible asset, "
            "incremental export, and index stages."
        )

    paths = _resolved_paths(provider, archive_root)

    if fresh:
        clear_generated_data(paths, progress=progress)
    else:
        migrate_legacy_archive(paths, legacy_root, progress=progress)
        for directory in (paths.downloads, paths.assets, paths.reports):
            directory.mkdir(parents=True, exist_ok=True)

    migrate_output_layout(paths, progress=progress)
    migrate_json_storage(paths, progress=progress)

    resolved_source: Path | None = None
    import_result: Any | None = None
    inventory_result: InventoryResult | None = None
    manifest_result: AssetManifestResult | None = None
    export_result: BatchExportResult | None = None

    if not convert_only:
        resolved_source = (
            Path(source_bundle).expanduser().resolve()
            if source_bundle is not None
            else require_source_bundle(
                provider,
                download_directories=download_directories,
                progress=progress,
            )
        )
        import_result = _call_stage(
            f"1/5 - Import {provider.display_name} archive bundle",
            lambda: provider.importer(
                resolved_source,
                archive_root=paths.root,
                progress=progress,
            ),
            progress=progress,
        )
        if getattr(import_result, "success", True) is False:
            raise RuntimeError(
                f"Step failed: 1/5 - Import {provider.display_name} archive bundle"
            )

    if not _conversation_files(paths.downloads):
        raise FileNotFoundError(
            "No conversation JSON/XZ files were found in the downloads directory."
        )

    if not skip_assets:
        inventory_result = _call_stage(
            "2/5 - Inventory media references",
            lambda: inventory_media(
                paths.downloads,
                paths.reports,
                progress=progress,
            ),
            progress=progress,
        )
        _emit(progress)
        _emit(progress, render_inventory_summary(inventory_result))

        manifest_result = _call_stage(
            "3/5 - Build asset manifest",
            lambda: build_asset_manifest(
                paths.downloads,
                paths.reports,
                progress=progress,
            ),
            progress=progress,
        )
        _emit(progress)
        _emit(progress, render_manifest_summary(manifest_result))
    else:
        _emit(progress, "\nAssets skipped by request.")

    batch_file = paths.reports / "current-batch.json"
    batch_data: dict[str, Any] | None = None
    export_skipped = False
    if not convert_only and batch_file.is_file():
        batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
        if not batch_data.get("conversation_files"):
            _emit(progress, "\nNo new or larger conversations to export.")
            _emit(progress, "Existing local archive was preserved.")
            export_skipped = True

    if not export_skipped:
        export_result = _call_stage(
            "4/5 - Export new or larger conversations",
            lambda: export_normalized_batch(
                provider,
                archive_root=paths.root,
                batch_file=None if convert_only else batch_file,
                overwrite_all=True,
                progress=progress,
            ),
            progress=progress,
        )
        if not export_result.success:
            raise RuntimeError(
                "Step failed with exit code 1: 4/5 - Export new or larger conversations"
            )

    index_result: IndexUpdateResult = _call_stage(
        "5/5 - Update archive search index",
        lambda: update_normalized_index(
            provider,
            paths.root,
            downloads_dir=paths.downloads,
            database_path=paths.database,
            progress=progress,
        ),
        progress=progress,
    )

    if validate_normalized:
        validation_sources = _resolve_validation_sources(
            paths,
            convert_only=convert_only,
            batch_data=batch_data,
        )
        if validation_sources:
            _emit(progress)
            _emit(progress, "Running normalized provider validation (non-destructive)…")
            try:
                run_normalized_shadow_validation(
                    provider,
                    validation_sources,
                    archive_root=paths.root,
                    production_database=paths.database,
                    compare_with_legacy_oracle=True,
                    progress=progress,
                )
            except Exception as error:  # Validation must never invalidate a successful archive.
                _emit(progress, f"WARNING: normalized shadow validation failed: {error}")
        else:
            _emit(progress, "Normalized shadow validation: no changed conversations to check.")

    source_deleted = False
    if resolved_source is not None and delete_source:
        source_deleted = delete_consumed_source_bundle(
            resolved_source,
            progress=progress,
        )

    _emit(progress)
    _emit(progress, "Archive completed successfully.")
    _emit(progress, f"Provider    : {provider.display_name}")
    _emit(progress, f"Archive root: {paths.root}")
    _emit(progress, f"DOCX files : {paths.root}")

    return ArchivePipelineResult(
        paths=paths,
        source_bundle=resolved_source,
        import_result=import_result,
        inventory_result=inventory_result,
        manifest_result=manifest_result,
        export_result=export_result,
        index_result=index_result,
        export_skipped=export_skipped,
        source_bundle_deleted=source_deleted,
    )


__all__ = ["archive_provider_bundle"]
