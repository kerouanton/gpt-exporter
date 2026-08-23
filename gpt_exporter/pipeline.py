"""In-process archive workflow for GPT Exporter.

This module owns the v2.8 archive-stage ordering while calling reusable Python
APIs directly.  It is deliberately synchronous and UI-agnostic: a CLI may pass
``print`` as the progress callback, while a GUI worker can route the same lines
to its log window without launching another GPT Exporter Python script.
"""

from __future__ import annotations

import json
import lzma
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from gpt_exporter.archive.importer import ImportBundleResult, import_bundle
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
from gpt_exporter.export.batch import BatchExportResult, export_batch
from gpt_exporter.index import IndexUpdateResult, update_index as update_archive_index
from gpt_exporter.paths import ArchivePaths, default_archive_paths, default_user_profile


ProgressCallback = Callable[[str], None]
SOURCE_BUNDLE_NAME = "chatgpt-archive-source.json"
GENERATED_DIRECTORY_NAMES = ("downloads", "assets", "reports")
LEGACY_DATA_DIRECTORY_NAMES = ("downloads", "assets", "exports", "reports")


@dataclass(frozen=True, slots=True)
class ArchivePipelineResult:
    """Structured result of one complete archive workflow."""

    paths: ArchivePaths
    source_bundle: Path | None
    import_result: ImportBundleResult | None
    inventory_result: InventoryResult | None
    manifest_result: AssetManifestResult | None
    export_result: BatchExportResult | None
    index_result: IndexUpdateResult
    export_skipped: bool
    source_bundle_deleted: bool



def _emit(progress: ProgressCallback | None, message: str = "") -> None:
    if progress is not None:
        progress(message)



def _step_heading(progress: ProgressCallback | None, label: str) -> None:
    _emit(progress)
    _emit(progress, "=" * 72)
    _emit(progress, label)
    _emit(progress, "=" * 72)



def _resolved_paths(archive_root: Path | str | None) -> ArchivePaths:
    if archive_root is None:
        root = default_archive_paths().root
    else:
        root = Path(archive_root).expanduser().resolve()
    return ArchivePaths.from_root(root)



def clear_generated_data(
    paths: ArchivePaths,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Apply the v2.8 ``--fresh`` cleanup to an explicit archive."""

    for directory in (paths.downloads, paths.assets, paths.reports):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)

    legacy_exports = paths.root / "exports"
    for directory in (paths.markdown, legacy_exports):
        if directory.exists():
            shutil.rmtree(directory)

    paths.root.mkdir(parents=True, exist_ok=True)
    for docx_path in paths.root.glob("*.docx"):
        docx_path.unlink()



def migrate_legacy_archive(
    paths: ArchivePaths,
    legacy_root: Path | str | None,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Conservatively move old in-project archive data to the archive root."""

    if legacy_root is None:
        return

    source_root = Path(legacy_root)
    conflicts: list[tuple[Path, Path]] = []

    for name in LEGACY_DATA_DIRECTORY_NAMES:
        source = source_root / name
        destination = paths.root / name

        if not source.exists():
            continue

        if destination.exists():
            destination_has_data = (
                not destination.is_dir()
                or any(
                    item.is_file() or item.is_symlink()
                    for item in destination.rglob("*")
                )
            )
            if destination_has_data:
                conflicts.append((source, destination))
                continue
            shutil.rmtree(destination)

        paths.root.mkdir(parents=True, exist_ok=True)
        _emit(progress)
        _emit(progress, f"Migrating legacy archive directory: {source}")
        _emit(progress, f"                               -> {destination}")
        shutil.move(str(source), str(destination))

    if conflicts:
        details = "\n".join(
            f"  legacy: {source}\n  target: {destination}"
            for source, destination in conflicts
        )
        raise RuntimeError(
            "Archive data exists both inside the project and under Documents. "
            "Automatic migration was stopped to avoid overwriting data.\n"
            f"{details}"
        )



def migrate_output_layout(
    paths: ArchivePaths,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Move legacy DOCX exports to the archive root and discard legacy Markdown."""

    legacy_exports = paths.root / "exports"
    legacy_markdown = legacy_exports / "markdown"
    legacy_docx = legacy_exports / "docx"
    paths.root.mkdir(parents=True, exist_ok=True)

    legacy_docx_files = sorted(legacy_docx.glob("*.docx")) if legacy_docx.is_dir() else []
    conflicts: list[tuple[Path, Path]] = []
    duplicates: set[Path] = set()

    for source in legacy_docx_files:
        destination = paths.root / source.name
        if not destination.exists():
            continue
        if destination.read_bytes() == source.read_bytes():
            duplicates.add(source)
        else:
            conflicts.append((source, destination))

    if conflicts:
        details = "\n".join(
            f"  legacy: {source}\n  target: {destination}"
            for source, destination in conflicts
        )
        raise RuntimeError(
            "DOCX files exist both in the legacy exports directory and at the "
            "archive root with different contents. Migration was stopped before "
            "moving or deleting output files.\n"
            f"{details}"
        )

    for source in legacy_docx_files:
        destination = paths.root / source.name
        if source in duplicates:
            source.unlink()
            _emit(progress, f"Removed duplicate legacy DOCX: {source}")
            continue
        source.replace(destination)
        _emit(progress, f"Moved legacy DOCX: {source.name} -> {destination}")

    if legacy_markdown.exists():
        shutil.rmtree(legacy_markdown)
        _emit(progress, f"Removed legacy Markdown directory: {legacy_markdown}")

    for directory in (legacy_docx, legacy_exports):
        if directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass



def compress_json_file_transactionally(
    source: Path,
    *,
    progress: ProgressCallback | None = None,
) -> Path:
    """Compress one legacy JSON file with the v2.8 verify-before-delete rule."""

    destination = source.with_name(source.name + ".xz")
    raw = source.read_bytes()

    if destination.is_file():
        try:
            with lzma.open(destination, "rb") as handle:
                existing = handle.read()
        except (OSError, EOFError, lzma.LZMAError) as exc:
            raise RuntimeError(
                f"Unable to verify existing XZ file: {destination}: {exc}"
            ) from exc
        if existing != raw:
            raise RuntimeError(
                "Both JSON and XZ versions exist with different contents: "
                f"{source.name} / {destination.name}"
            )
        source.unlink()
        return destination

    temp = destination.with_name(destination.name + ".tmp")
    try:
        with lzma.open(temp, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(raw)
        with lzma.open(temp, "rb") as handle:
            verified = handle.read()
        if verified != raw:
            raise RuntimeError(f"XZ verification failed: {source}")
        temp.replace(destination)
        source.unlink()
    finally:
        if temp.exists():
            temp.unlink()

    _emit(progress, f"Compressed legacy JSON: {source.name} -> {destination.name}")
    return destination



def migrate_json_storage(
    paths: ArchivePaths,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Migrate legacy uncompressed conversation/report JSON to XZ."""

    paths.downloads.mkdir(parents=True, exist_ok=True)
    legacy_conversations = sorted(
        path
        for path in paths.downloads.glob("*.json")
        if path.name != "download-index.json"
    )
    for source in legacy_conversations:
        compress_json_file_transactionally(source, progress=progress)

    paths.reports.mkdir(parents=True, exist_ok=True)
    for name in (
        "asset-download-index-v2.json",
        "asset-manifest.json",
        "inventory-media-report.json",
    ):
        source = paths.reports / name
        if source.is_file():
            compress_json_file_transactionally(source, progress=progress)



def windows_download_directories(
    environ: Mapping[str, str] | None = None,
    *,
    home: Path | None = None,
) -> list[Path]:
    """Return unique Windows Downloads candidates using the v2.8 order."""

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



def find_source_bundle_in_downloads(
    name: str = SOURCE_BUNDLE_NAME,
    *,
    download_directories: list[Path] | None = None,
    progress: ProgressCallback | None = None,
) -> Path | None:
    """Find the newest non-empty browser bundle in the usual Downloads folders."""

    directories = download_directories or windows_download_directories()
    matches: list[Path] = []
    for directory in directories:
        candidate = directory / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            matches.append(candidate)

    if not matches:
        return None

    source = max(matches, key=lambda path: path.stat().st_mtime)
    _emit(progress)
    _emit(progress, f"Found browser bundle in Windows Downloads: {source}")
    _emit(progress, "The bundle will be processed in place and deleted after a successful run.")
    return source



def print_bundle_creation_instructions(progress: ProgressCallback | None) -> None:
    _emit(progress)
    _emit(progress, "To generate chatgpt-archive-source.json:")
    _emit(progress, "  1. Open your web browser and go to https://chatgpt.com/")
    _emit(progress, "  2. Press F12 to open Developer Tools.")
    _emit(progress, "  3. Open the Console tab.")
    _emit(progress, "  4. Copy the complete contents of collect_chatgpt_archive.js.")
    _emit(progress, "  5. Paste the script into the console and run it.")
    _emit(progress, "  6. Leave the downloaded chatgpt-archive-source.json in Windows Downloads,")
    _emit(progress, "     then run archive_chats.py again. It will process the file in place.")



def require_source_bundle(
    *,
    download_directories: list[Path] | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    directories = download_directories or windows_download_directories()
    path = find_source_bundle_in_downloads(
        download_directories=directories,
        progress=progress,
    )
    if path is not None:
        return path

    print_bundle_creation_instructions(progress)
    searched = ", ".join(str(path) for path in directories)
    raise FileNotFoundError(
        f"Required file is missing or empty: {SOURCE_BUNDLE_NAME}. "
        f"Searched Windows Downloads locations: {searched}"
    )



def delete_consumed_source_bundle(
    path: Path,
    *,
    progress: ProgressCallback | None = None,
) -> bool:
    """Delete a consumed source bundle, warning rather than failing on error."""

    try:
        path.unlink()
    except OSError as exc:
        _emit(progress)
        _emit(progress, f"WARNING: archive succeeded, but the source bundle could not be deleted: {path}")
        _emit(progress, f"WARNING: {exc}")
        return False

    _emit(progress)
    _emit(progress, f"Deleted consumed browser bundle: {path}")
    return True



def _conversation_files(downloads_dir: Path) -> list[Path]:
    files = sorted(downloads_dir.glob("*.json.xz"))
    if not files:
        files = [
            path
            for path in downloads_dir.glob("*.json")
            if path.name != "download-index.json"
        ]
    return files



def _call_stage(label: str, operation, *, progress: ProgressCallback | None):
    _step_heading(progress, label)
    try:
        return operation()
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Step failed: {label}: {exc}") from exc



def archive_bundle(
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
    """Run the complete v2.8 archive workflow without internal Python subprocesses."""

    paths = _resolved_paths(archive_root)

    if fresh:
        clear_generated_data(paths, progress=progress)
    else:
        migrate_legacy_archive(paths, legacy_root, progress=progress)
        for directory in (paths.downloads, paths.assets, paths.reports):
            directory.mkdir(parents=True, exist_ok=True)

    migrate_output_layout(paths, progress=progress)
    migrate_json_storage(paths, progress=progress)

    resolved_source: Path | None = None
    import_result: ImportBundleResult | None = None
    inventory_result: InventoryResult | None = None
    manifest_result: AssetManifestResult | None = None
    export_result: BatchExportResult | None = None

    if not convert_only:
        resolved_source = (
            Path(source_bundle).expanduser().resolve()
            if source_bundle is not None
            else require_source_bundle(
                download_directories=download_directories,
                progress=progress,
            )
        )
        import_result = _call_stage(
            "1/5 - Import browser archive bundle",
            lambda: import_bundle(
                resolved_source,
                archive_root=paths.root,
                progress=progress,
            ),
            progress=progress,
        )
        if not import_result.success:
            raise RuntimeError(
                "Step failed with exit code 2: 1/5 - Import browser archive bundle"
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
            lambda: export_batch(
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

    index_result = _call_stage(
        "5/5 - Update archive search index",
        lambda: update_archive_index(
            paths.root,
            downloads_dir=paths.downloads,
            database_path=paths.database,
            progress=progress,
        ),
        progress=progress,
    )

    source_deleted = False
    if resolved_source is not None and delete_source:
        source_deleted = delete_consumed_source_bundle(
            resolved_source,
            progress=progress,
        )

    _emit(progress)
    _emit(progress, "Archive completed successfully.")
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


__all__ = [
    "ArchivePipelineResult",
    "SOURCE_BUNDLE_NAME",
    "archive_bundle",
    "clear_generated_data",
    "compress_json_file_transactionally",
    "delete_consumed_source_bundle",
    "find_source_bundle_in_downloads",
    "migrate_json_storage",
    "migrate_legacy_archive",
    "migrate_output_layout",
    "require_source_bundle",
    "windows_download_directories",
]
