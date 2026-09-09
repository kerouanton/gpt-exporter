"""Provider-neutral library API for converting Markdown to DOCX.

The public API always receives explicit input/output paths. The retained v2.8
renderer is package-local implementation detail; its historical standalone CLI
defaults are not part of this library contract.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Callable


ProgressCallback = Callable[[str], None]
_AUTHOR_AVATAR_PREFIX = "Author avatar: "


@dataclass(frozen=True, slots=True)
class DocxExportResult:
    """Structured result of one Markdown-to-DOCX conversion."""

    output_path: Path
    size_bytes: int
    skipped: bool


def _install_normalized_image_cache(implementation: ModuleType) -> None:
    """Reuse normalized image bytes only for the duration of one DOCX export."""
    if getattr(implementation, "_canonical_normalized_image_cache", False):
        return
    original_normalize = implementation.normalized_png_stream

    @lru_cache(maxsize=256)
    def normalized_bytes(path_text: str, mtime_ns: int, size: int) -> bytes:
        del mtime_ns, size
        return original_normalize(Path(path_text)).getvalue()

    def normalized_png_stream(image_path: Path):
        path = Path(image_path).resolve()
        stat = path.stat()
        return io.BytesIO(
            normalized_bytes(
                str(path),
                stat.st_mtime_ns,
                stat.st_size,
            )
        )

    implementation.normalized_png_stream = normalized_png_stream
    implementation._canonical_normalized_image_cache_clear = normalized_bytes.cache_clear
    implementation._canonical_normalized_image_cache = True


def _install_author_avatar_renderer(implementation: ModuleType) -> None:
    """Teach the retained renderer one provider-neutral canonical image role."""
    if getattr(implementation, "_canonical_author_avatar_renderer", False):
        return
    original_add_image = implementation.add_image

    def add_image(document, image_path: Path, alt_text: str) -> None:
        if not str(alt_text or "").startswith(_AUTHOR_AVATAR_PREFIX):
            original_add_image(document, image_path, alt_text)
            return
        paragraph = document.add_paragraph()
        paragraph.alignment = implementation.WD_PARAGRAPH_ALIGNMENT.LEFT
        try:
            run = paragraph.add_run()
            inline_shape = implementation.add_picture_with_fallback(
                run,
                image_path,
                0.38,
            )
            try:
                inline_shape._inline.docPr.set(
                    "descr",
                    implementation.xml_safe_text(alt_text),
                )
            except Exception:
                pass
        except Exception as error:
            implementation.logging.warning(
                "Unable to embed author avatar %s: %s: %s",
                image_path,
                type(error).__name__,
                error,
            )

    implementation.add_image = add_image
    implementation._canonical_author_avatar_renderer = True


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    """Load the retained package-local v2.8 Markdown renderer quietly."""

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        from . import _markdown_docx_v28
    _install_normalized_image_cache(_markdown_docx_v28)
    _install_author_avatar_renderer(_markdown_docx_v28)
    return _markdown_docx_v28


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
    """Convert one Markdown document to DOCX without invoking a provider CLI."""

    markdown_path = Path(markdown_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()

    if not markdown_path.is_file():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")
    if not overwrite and output_path.is_file() and output_path.stat().st_size > 0:
        return DocxExportResult(
            output_path=output_path,
            size_bytes=output_path.stat().st_size,
            skipped=True,
        )

    implementation = _implementation()
    cache_clear = getattr(implementation, "_canonical_normalized_image_cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            implementation.convert_markdown_to_docx(
                markdown_path=markdown_path,
                output_path=output_path,
                document_title=document_title,
            )
    finally:
        if cache_clear is not None:
            cache_clear()

    _forward_progress(captured, progress)

    if not output_path.is_file() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"DOCX conversion did not create a valid file: {output_path}")

    return DocxExportResult(
        output_path=output_path,
        size_bytes=output_path.stat().st_size,
        skipped=False,
    )
