"""In-process batch export orchestration for GPT Exporter.

This module replaces the historical ``export_all.py`` pattern of loading other
Python scripts from disk and driving their ``main()`` functions through
``sys.argv``.  All work is delegated to explicit library APIs instead.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gpt_exporter.archive.audit import AssetAuditResult, audit_asset_references
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_markdown
from gpt_exporter.paths import default_archive_paths


DOWNLOAD_DIRECTORY = "downloads"
PERSISTENT_MARKDOWN_DIRECTORY = "markdown"
ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class BatchExportResult:
    """Structured result of one batch export operation."""

    archive_root: Path
    markdown_directory: Path
    requested: int
    markdown_converted: int
    markdown_skipped: int
    markdown_failed: tuple[Path, ...]
    docx_converted: int
    docx_skipped: int
    docx_failed: tuple[Path, ...]
    audit_result: AssetAuditResult | None
    temporary_markdown_removed: bool
    markdown_only: bool
    success: bool


def conversation_markdown_name(json_path: Path) -> str:
    """Return the stable Markdown filename for one archived conversation."""

    if json_path.name.lower().endswith(".json.xz"):
        return json_path.name[:-8] + ".md"
    return json_path.with_suffix(".md").name


def conversation_docx_name(json_path: Path) -> str:
    """Return the stable DOCX filename for one archived conversation."""

    return Path(conversation_markdown_name(json_path)).with_suffix(".docx").name


def _emit(progress: ProgressCallback | None, message: str = "") -> None:
    if progress is not None:
        progress(message)


def _load_batch_conversations(
    downloads_directory: Path,
    batch_file: Path | None,
    progress: ProgressCallback | None,
) -> list[Path]:
    if batch_file is not None:
        batch_file = Path(batch_file).expanduser().resolve()
        if not batch_file.is_file():
            raise FileNotFoundError(f"batch file not found: {batch_file}")

        batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
        batch_names = batch_data.get("conversation_files", [])
        if not isinstance(batch_names, list):
            raise ValueError("invalid conversation_files in batch file")

        json_files: list[Path] = []
        for name in batch_names:
            if not isinstance(name, str):
                continue
            candidate = downloads_directory / Path(name).name
            if candidate.is_file():
                json_files.append(candidate)
            else:
                _emit(progress, f"WARNING: batch JSON not found: {candidate.name}")
        return sorted(json_files)

    json_files = sorted(downloads_directory.glob("*.json.xz"))
    if not json_files:
        json_files = sorted(
            path
            for path in downloads_directory.glob("*.json")
            if path.name != "download-index.json"
        )
    return json_files


def _audit_lines(result: AssetAuditResult) -> list[str]:
    """Render the useful v2.8 audit summary for workflow logs."""

    report = result.report
    unreferenced = report.get("unreferenced_local_assets", [])
    missing_local = report.get("referenced_missing_local_assets", [])
    duplicates = report.get("duplicate_local_asset_ids", [])
    unidentified = report.get("unidentified_local_asset_files", [])

    if not isinstance(unreferenced, list):
        unreferenced = []
    if not isinstance(missing_local, list):
        missing_local = []
    if not isinstance(duplicates, list):
        duplicates = []
    if not isinstance(unidentified, list):
        unidentified = []

    lines = [
        "",
        "Asset reference audit",
        "=====================",
        f"Archive root               : {result.archive_root}",
        f"Physical asset files       : {report.get('asset_files_scanned', 0)}",
        f"Unique local asset IDs     : {report.get('unique_local_asset_ids', 0)}",
        f"DOCX files scanned         : {report.get('docx_files_scanned', 0)}",
        f"Markdown files scanned     : {report.get('markdown_files_scanned', 0)}",
        f"Rendered asset IDs found   : {report.get('referenced_asset_ids', 0)}",
        f"Unreferenced local assets  : {len(unreferenced)}",
        f"Referenced but local-missing: {len(missing_local)}",
        f"Duplicate local asset IDs  : {len(duplicates)}",
        f"Unidentified asset files   : {len(unidentified)}",
        f"Report                     : {result.report_path}",
    ]

    category_counts = report.get("unreferenced_category_counts", {})
    if isinstance(category_counts, dict) and category_counts:
        lines.extend(["", "Unreferenced asset classification", "---------------------------------"])
        for category, count in sorted(category_counts.items()):
            lines.append(f"  {str(category):27s}: {int(count):5d}")

    if not unreferenced and not missing_local and not unidentified:
        lines.extend(["", "Asset reference audit completed with no discrepancies."])

    return lines


def export_batch(
    *,
    archive_root: Path | str | None = None,
    batch_file: Path | str | None = None,
    overwrite_markdown: bool = False,
    overwrite_docx: bool = False,
    overwrite_all: bool = False,
    markdown_only: bool = False,
    keep_markdown: bool = False,
    progress: ProgressCallback | None = None,
) -> BatchExportResult:
    """Export archived conversation JSON files through the library APIs.

    The operation preserves the v2.8 batch semantics: persistent Markdown is
    skipped unless explicitly overwritten, temporary Markdown is removed only
    after a fully successful DOCX run, and the cumulative asset audit runs only
    after successful export work.
    """

    if archive_root is None:
        resolved_root = default_archive_paths().root
    else:
        resolved_root = Path(archive_root).expanduser().resolve()

    downloads_directory = resolved_root / DOWNLOAD_DIRECTORY
    persistent_markdown_directory = resolved_root / PERSISTENT_MARKDOWN_DIRECTORY

    if not downloads_directory.exists():
        raise FileNotFoundError(f"missing path: {downloads_directory}")

    resolved_batch = (
        Path(batch_file).expanduser().resolve()
        if batch_file is not None
        else None
    )
    json_files = _load_batch_conversations(
        downloads_directory,
        resolved_batch,
        progress,
    )
    if not json_files:
        raise FileNotFoundError(f"no JSON files found in {downloads_directory}")

    persistent_markdown = markdown_only or keep_markdown
    temporary_markdown_directory: Path | None = None

    if persistent_markdown:
        markdown_directory = persistent_markdown_directory
        markdown_directory.mkdir(parents=True, exist_ok=True)
        _emit(progress, f"Persistent Markdown directory: {markdown_directory}")
    else:
        temporary_markdown_directory = Path(
            tempfile.mkdtemp(prefix="gpt-exporter-markdown-")
        )
        markdown_directory = temporary_markdown_directory
        _emit(progress, f"Temporary Markdown directory: {markdown_directory}")

    requested = len(json_files)
    markdown_converted = 0
    markdown_skipped = 0
    markdown_failed: list[Path] = []

    _emit(progress, "Using Markdown export library in-process.")
    _emit(progress)
    _emit(progress, "Markdown intermediate export")
    _emit(progress, "============================")
    _emit(progress, f"JSON files: {requested}")

    overwrite_markdown_effective = overwrite_markdown or overwrite_all
    for index, json_path in enumerate(json_files, start=1):
        markdown_path = markdown_directory / conversation_markdown_name(json_path)
        _emit(progress)
        _emit(progress, f"[{index}/{requested}] {json_path.name}")

        if (
            persistent_markdown
            and not overwrite_markdown_effective
            and markdown_path.is_file()
            and markdown_path.stat().st_size > 0
        ):
            _emit(progress, f"SKIP: {markdown_path.name}")
            markdown_skipped += 1
            continue

        try:
            export_markdown(
                json_path,
                markdown_path,
                asset_index_path=resolved_root / "reports" / ASSET_INDEX_NAME,
                asset_directory=resolved_root / "assets",
            )
        except Exception as exc:
            _emit(progress, f"FAILED: {json_path.name}: {exc}")
            markdown_failed.append(json_path)
            continue

        markdown_converted += 1
        _emit(progress, f"Markdown export created: {markdown_path}")

    _emit(progress)
    _emit(progress, "Markdown summary")
    _emit(progress, "================")
    _emit(progress, f"Requested : {requested}")
    _emit(progress, f"Converted : {markdown_converted}")
    _emit(progress, f"Skipped   : {markdown_skipped}")
    _emit(progress, f"Failed    : {len(markdown_failed)}")

    if markdown_failed:
        _emit(progress)
        _emit(progress, "Failed JSON files")
        _emit(progress, "-----------------")
        for path in markdown_failed:
            _emit(progress, path.name)

    audit_result: AssetAuditResult | None = None

    if markdown_only:
        success = not markdown_failed
        if success:
            _emit(progress)
            _emit(progress, "Running cumulative asset reference audit...")
            audit_result = audit_asset_references(resolved_root)
            for line in _audit_lines(audit_result):
                _emit(progress, line)

        return BatchExportResult(
            archive_root=resolved_root,
            markdown_directory=markdown_directory,
            requested=requested,
            markdown_converted=markdown_converted,
            markdown_skipped=markdown_skipped,
            markdown_failed=tuple(markdown_failed),
            docx_converted=0,
            docx_skipped=0,
            docx_failed=(),
            audit_result=audit_result,
            temporary_markdown_removed=False,
            markdown_only=True,
            success=success,
        )

    _emit(progress)
    _emit(progress, "Using DOCX export library in-process.")
    _emit(progress)
    _emit(progress, "DOCX batch export")
    _emit(progress, "=================")

    docx_converted = 0
    docx_skipped = 0
    docx_failed: list[Path] = []
    overwrite_docx_effective = overwrite_docx or overwrite_all

    for json_path in json_files:
        markdown_path = markdown_directory / conversation_markdown_name(json_path)
        if not markdown_path.is_file():
            _emit(progress, f"FAILED: Markdown missing for DOCX: {markdown_path.name}")
            docx_failed.append(json_path)
            continue

        docx_path = resolved_root / conversation_docx_name(json_path)
        try:
            result = export_docx(
                markdown_path,
                docx_path,
                overwrite=overwrite_docx_effective,
                progress=progress,
            )
            if result.skipped:
                docx_skipped += 1
                _emit(progress, f"SKIP existing DOCX: {docx_path}")
            else:
                docx_converted += 1
        except Exception as exc:
            _emit(progress, f"DOCX failed: {markdown_path.name}: {exc}")
            docx_failed.append(json_path)

    success = not markdown_failed and not docx_failed

    if success:
        _emit(progress)
        _emit(progress, "Running cumulative asset reference audit...")
        try:
            audit_result = audit_asset_references(resolved_root)
            for line in _audit_lines(audit_result):
                _emit(progress, line)
        except Exception as exc:
            _emit(progress, f"ERROR: asset reference audit failed: {exc}")
            success = False

    temporary_markdown_removed = False
    if temporary_markdown_directory is not None:
        if success:
            shutil.rmtree(temporary_markdown_directory, ignore_errors=False)
            temporary_markdown_removed = True
            _emit(progress)
            _emit(
                progress,
                f"Removed temporary Markdown directory: {temporary_markdown_directory}",
            )
        else:
            _emit(progress)
            _emit(
                progress,
                "WARNING: DOCX conversion did not fully succeed. Temporary Markdown "
                f"was preserved for diagnosis: {temporary_markdown_directory}",
            )

    return BatchExportResult(
        archive_root=resolved_root,
        markdown_directory=markdown_directory,
        requested=requested,
        markdown_converted=markdown_converted,
        markdown_skipped=markdown_skipped,
        markdown_failed=tuple(markdown_failed),
        docx_converted=docx_converted,
        docx_skipped=docx_skipped,
        docx_failed=tuple(docx_failed),
        audit_result=audit_result,
        temporary_markdown_removed=temporary_markdown_removed,
        markdown_only=False,
        success=success,
    )
