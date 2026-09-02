"""Derived exports from provider-neutral normalized conversations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gpt_exporter.model import Conversation

from .docx import DocxExportResult, export_docx
from .normalized_markdown import render_conversation_markdown


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class NormalizedExportResult:
    markdown_path: Path
    docx_result: DocxExportResult | None


def export_normalized_conversation(
    conversation: Conversation,
    markdown_path: Path | str,
    *,
    docx_path: Path | str | None = None,
    include_timestamps: bool = False,
    overwrite: bool = False,
    progress: ProgressCallback | None = None,
) -> NormalizedExportResult:
    """Write Markdown and optionally DOCX from the common conversation model."""

    markdown = Path(markdown_path).expanduser().resolve()
    markdown.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_conversation_markdown(
        conversation,
        include_timestamps=include_timestamps,
    )
    markdown.write_text(rendered, encoding="utf-8", newline="\n")
    if progress is not None:
        progress(f"Markdown: {markdown}")

    docx_result: DocxExportResult | None = None
    if docx_path is not None:
        # Historical batch export lets the Markdown H1 provide the document title.
        # Passing document_title would add a second Word Title paragraph.
        docx_result = export_docx(
            markdown,
            Path(docx_path).expanduser().resolve(),
            document_title=None,
            overwrite=overwrite,
            progress=progress,
        )

    return NormalizedExportResult(
        markdown_path=markdown,
        docx_result=docx_result,
    )


__all__ = ["NormalizedExportResult", "export_normalized_conversation"]
