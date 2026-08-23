"""Library API for converting GPT Exporter Markdown to DOCX.

The stable v2.9 API keeps CLI concerns out of callers.  The current v2.8 DOCX
implementation remains in the historical ``export_docx.py`` module for now and
is loaded lazily behind this boundary.  The adapter captures the legacy
progress prints and forwards them only when a callback is supplied, so library
calls are otherwise quiet and do not depend on console output.
"""

from __future__ import annotations

import contextlib
import importlib
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Callable


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class DocxExportResult:
    """Structured result of one Markdown-to-DOCX conversion."""

    output_path: Path
    size_bytes: int
    skipped: bool


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    """Load the unchanged v2.8 converter lazily and suppress import diagnostics."""

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return importlib.import_module("export_docx")


def _forward_progress(buffer: io.StringIO, progress: ProgressCallback | None) -> None:
    if progress is None:
        return

    for line in buffer.getvalue().splitlines():
        if line.strip():
            progress(line)


def export_docx(
    markdown_path: Path | str,
    output_path: Path | str,
    *,
    document_title: str | None = None,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
) -> DocxExportResult:
    """Convert one Markdown document to DOCX without invoking a CLI.

    Exceptions are allowed to propagate.  ``overwrite=False`` preserves the
    v2.8 CLI behavior of keeping an existing non-empty DOCX untouched.
    """

    markdown_path = Path(markdown_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()

    if not markdown_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    if (
        not overwrite
        and output_path.is_file()
        and output_path.stat().st_size > 0
    ):
        return DocxExportResult(
            output_path=output_path,
            size_bytes=output_path.stat().st_size,
            skipped=True,
        )

    implementation = _implementation()
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        implementation.convert_markdown_to_docx(
            markdown_path=markdown_path,
            output_path=output_path,
            document_title=document_title,
        )

    _forward_progress(captured, progress)

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"DOCX conversion did not create a valid file: {output_path}")

    return DocxExportResult(
        output_path=output_path,
        size_bytes=output_path.stat().st_size,
        skipped=False,
    )
