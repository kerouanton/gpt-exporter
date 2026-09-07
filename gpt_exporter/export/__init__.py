"""Provider-neutral export APIs for GPT Exporter."""

from .docx import DocxExportResult, export_docx
from .markdown import (
    MarkdownExportResult,
    export_canonical_markdown,
    export_markdown,
    render_canonical_markdown,
)


def export_batch(*args, **kwargs):
    """Lazy compatibility entry point for the historical ChatGPT batch exporter."""
    from .batch import export_batch as implementation
    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "BatchExportResult":
        from .batch import BatchExportResult
        return BatchExportResult
    raise AttributeError(name)


__all__ = [
    "BatchExportResult",
    "DocxExportResult",
    "MarkdownExportResult",
    "export_batch",
    "export_canonical_markdown",
    "export_docx",
    "export_markdown",
    "render_canonical_markdown",
]
