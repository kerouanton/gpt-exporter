"""Legacy canonical renderer v7 focused on semantic preservation.

The historical Word document remains immutable. Its representable semantics are
converted to Markdown, then the ordinary GPT Exporter Markdown -> DOCX renderer
produces the normalized document.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gpt_exporter.export import _legacy_docx as _docx_renderer

from . import canonical_docx as _base
from .word_markdown import source_block_markdown


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v7"
CanonicalLegacyDocxResult = _base.CanonicalLegacyDocxResult
canonical_output_name = _base.canonical_output_name


def _add_inline_content_with_html_breaks(original):
    """Map the common Markdown-table <br> convention to a real Word break."""
    def wrapped(paragraph, inline_token, markdown_path, output_path):
        changed = []
        for token in inline_token.children or []:
            if token.type == "html_inline" and token.content.strip().casefold() in {
                "<br>", "<br/>", "<br />",
            }:
                changed.append((token, token.type))
                token.type = "hardbreak"
        try:
            return original(paragraph, inline_token, markdown_path, output_path)
        finally:
            for token, token_type in changed:
                token.type = token_type
    return wrapped


def _with_v7_semantic_renderer(function, *args, **kwargs):
    previous_source_renderer = _base._source_block_markdown
    previous_version = _base.CANONICAL_LEGACY_DOCX_VERSION
    previous_inline_renderer = _docx_renderer.add_inline_content

    _base._source_block_markdown = source_block_markdown
    _base.CANONICAL_LEGACY_DOCX_VERSION = CANONICAL_LEGACY_DOCX_VERSION
    _docx_renderer.add_inline_content = _add_inline_content_with_html_breaks(previous_inline_renderer)
    try:
        return function(*args, **kwargs)
    finally:
        _base._source_block_markdown = previous_source_renderer
        _base.CANONICAL_LEGACY_DOCX_VERSION = previous_version
        _docx_renderer.add_inline_content = previous_inline_renderer


def build_legacy_markdown(
    conversation: dict[str, Any],
    *,
    source_docx: Path | None = None,
    asset_export=None,
    markdown_base: Path | None = None,
) -> str:
    return _with_v7_semantic_renderer(
        _base.build_legacy_markdown,
        conversation,
        source_docx=source_docx,
        asset_export=asset_export,
        markdown_base=markdown_base,
    )


def export_legacy_canonical_docx(
    conversation: dict[str, Any],
    output_dir: Path,
    *,
    overwrite: bool = False,
    docx_root: Path | None = None,
) -> CanonicalLegacyDocxResult:
    return _with_v7_semantic_renderer(
        _base.export_legacy_canonical_docx,
        conversation,
        output_dir,
        overwrite=overwrite,
        docx_root=docx_root,
    )
