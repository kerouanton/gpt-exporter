"""Provider-neutral batch export from normalized conversations.

This preserves the historical batch orchestration contract while replacing the
source-specific Markdown conversion step with ``ExporterProvider`` normalization
plus the common renderer. DOCX conversion remains shared. The historical
cumulative asset audit is still available, but callers may disable it for the
normal incremental archive path because it rescans the complete archive.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from gpt_exporter.archive.audit import AssetAuditResult, audit_asset_references
from gpt_exporter.providers.base import ExporterProvider, ProgressCallback

from .batch import (
    ASSET_INDEX_NAME,
    DOWNLOAD_DIRECTORY,
    PERSISTENT_MARKDOWN_DIRECTORY,
    BatchExportResult,
    _audit_lines,
    _load_batch_conversations,
    conversation_docx_name,
    conversation_markdown_name,
)
from .docx import export_docx
from .normalized import export_normalized_conversation


def _emit(progress: ProgressCallback | None, message: str = "") -> None:
    if progress is not None:
        progress(message)


def export_normalized_batch(
    provider: ExporterProvider,
    *,
    archive_root: Path | str,
    batch_file: Path | str | None = None,
    overwrite_markdown: bool = False,
    overwrite_docx: bool = False,
    overwrite_all: bool = False,
    markdown_only: bool = False,
    keep_markdown: bool = False,
    run_asset_audit: bool = True,
    progress: ProgressCallback | None = None,
) -> BatchExportResult:
    """Export one archive batch through the provider-neutral display model.

    ``run_asset_audit`` defaults to ``True`` so direct/library callers retain
    historical behavior. The daily archive pipeline may disable it because the
    cumulative audit opens every DOCX and every preserved conversation JSON.
    """

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

    _emit(progress, f"Using normalized {provider.display_name} Markdown export in-process.")
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
            conversation = provider.normalize_conversation(
                json_path,
                asset_directory=resolved_root / "assets",
                markdown_directory=markdown_directory,
                asset_index_path=resolved_root / "reports" / ASSET_INDEX_NAME,
            )
            export_normalized_conversation(
                conversation,
                markdown_path,
                overwrite=True,
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
        if success and run_asset_audit:
            _emit(progress)
            _emit(progress, "Running cumulative asset reference audit...")
            audit_result = audit_asset_references(resolved_root)
            for line in _audit_lines(audit_result):
                _emit(progress, line)
        elif success:
            _emit(progress)
            _emit(progress, "Cumulative asset reference audit skipped for incremental run.")
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
    if success and run_asset_audit:
        _emit(progress)
        _emit(progress, "Running cumulative asset reference audit...")
        try:
            audit_result = audit_asset_references(resolved_root)
            for line in _audit_lines(audit_result):
                _emit(progress, line)
        except Exception as exc:
            _emit(progress, f"ERROR: asset reference audit failed: {exc}")
            success = False
    elif success:
        _emit(progress)
        _emit(progress, "Cumulative asset reference audit skipped for incremental run.")

    temporary_markdown_removed = False
    if temporary_markdown_directory is not None:
        if success:
            shutil.rmtree(temporary_markdown_directory, ignore_errors=False)
            temporary_markdown_removed = True
            _emit(progress)
            _emit(progress, f"Removed temporary Markdown directory: {temporary_markdown_directory}")
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


__all__ = ["export_normalized_batch"]
