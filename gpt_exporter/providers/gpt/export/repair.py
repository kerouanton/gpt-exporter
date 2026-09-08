"""Repair missing ChatGPT DOCX exports from already archived JSON sources."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .batch import BatchExportResult, export_batch


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class MissingDocxRepairResult:
    """Structured result of one missing-DOCX repair pass."""

    archive_root: Path
    missing_sources: tuple[Path, ...]
    batch_result: BatchExportResult | None

    @property
    def repaired_count(self) -> int:
        return 0 if self.batch_result is None else self.batch_result.docx_converted

    @property
    def success(self) -> bool:
        return self.batch_result is None or self.batch_result.success


def conversation_docx_name(source: Path | str) -> str:
    """Return the root-level DOCX name derived from one archived JSON source."""

    path = Path(source)
    name = path.name
    if name.lower().endswith(".json.xz"):
        return name[:-8] + ".docx"
    if name.lower().endswith(".json"):
        return name[:-5] + ".docx"
    return path.with_suffix(".docx").name


def archived_conversation_sources(archive_root: Path | str) -> tuple[Path, ...]:
    """Return archived conversation JSON/XZ sources in deterministic order."""

    root = Path(archive_root).expanduser().resolve()
    downloads = root / "downloads"
    if not downloads.is_dir():
        return ()

    compressed = tuple(sorted(downloads.glob("*.json.xz")))
    if compressed:
        return compressed

    return tuple(
        sorted(
            path
            for path in downloads.glob("*.json")
            if path.name != "download-index.json"
        )
    )


def find_missing_docx_sources(archive_root: Path | str) -> tuple[Path, ...]:
    """Return sources whose derived DOCX is absent or zero-length."""

    root = Path(archive_root).expanduser().resolve()
    missing: list[Path] = []
    for source in archived_conversation_sources(root):
        docx = root / conversation_docx_name(source)
        try:
            usable = docx.is_file() and docx.stat().st_size > 0
        except OSError:
            usable = False
        if not usable:
            missing.append(source)
    return tuple(missing)


def _emit(progress: ProgressCallback | None, message: str = "") -> None:
    if progress is not None:
        progress(message)


def regenerate_missing_docx(
    archive_root: Path | str,
    *,
    progress: ProgressCallback | None = None,
) -> MissingDocxRepairResult:
    """Regenerate only missing/empty DOCX files from archived JSON/XZ sources.

    The operation never recollects or rewrites conversation JSON.  It creates a
    temporary export batch containing only repair candidates and delegates to
    the normal ChatGPT batch exporter so Markdown/DOCX rendering semantics stay
    identical to ordinary archive runs.
    """

    root = Path(archive_root).expanduser().resolve()
    missing = find_missing_docx_sources(root)

    _emit(progress, "Scanning archived conversations for missing DOCX exports...")
    _emit(progress, f"Archive root: {root}")
    _emit(progress, f"Missing or empty DOCX files: {len(missing)}")

    if not missing:
        _emit(progress, "Nothing to regenerate.")
        return MissingDocxRepairResult(
            archive_root=root,
            missing_sources=(),
            batch_result=None,
        )

    for source in missing:
        _emit(progress, f"  {source.name}")

    with tempfile.TemporaryDirectory(prefix="gpt-exporter-repair-") as temporary:
        batch_file = Path(temporary) / "missing-docx-batch.json"
        batch_file.write_text(
            json.dumps(
                {"conversation_files": [source.name for source in missing]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        _emit(progress)
        _emit(progress, "Regenerating missing DOCX exports from archived JSON...")
        batch_result = export_batch(
            archive_root=root,
            batch_file=batch_file,
            overwrite_all=True,
            progress=progress,
        )

    return MissingDocxRepairResult(
        archive_root=root,
        missing_sources=missing,
        batch_result=batch_result,
    )


__all__ = [
    "MissingDocxRepairResult",
    "archived_conversation_sources",
    "conversation_docx_name",
    "find_missing_docx_sources",
    "regenerate_missing_docx",
]
