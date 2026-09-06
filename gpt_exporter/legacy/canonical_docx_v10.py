"""Legacy canonical renderer v10 focused on semantic preservation.

The historical Word document remains immutable. Representable Word semantics are
converted to Markdown, while historical raw-Markdown paragraphs are preserved
verbatim and malformed fences are contained within their original Word paragraph.
The ordinary GPT Exporter Markdown -> DOCX renderer then produces the normalized
document.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gpt_exporter.export import _legacy_docx as _docx_renderer

from . import canonical_docx as _base
from .word_markdown import source_block_markdown as _source_block_markdown


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v10"
CanonicalLegacyDocxResult = _base.CanonicalLegacyDocxResult
canonical_output_name = _base.canonical_output_name


_NESTED_LIST_RE = re.compile(r"^(?P<indent>(?:  )+)(?P<marker>(?:-|1\.)\s)", re.MULTILINE)


def source_block_markdown(source_docx: Path) -> dict[int, str]:
    """Return semantic source blocks with CommonMark-safe nested-list indents."""
    blocks = _source_block_markdown(source_docx)

    def normalize_indent(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            levels = len(match.group("indent")) // 2
            return ("    " * levels) + match.group("marker")

        return _NESTED_LIST_RE.sub(replace, text)

    return {order: normalize_indent(text) for order, text in blocks.items()}


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


def _turn_body_without_range_expansion(original):
    """Restore only explicit turn source orders, never hidden sentinel gaps."""
    def wrapped(turn, source_blocks, assets, markdown_base):
        if source_blocks is None:
            return original(turn, source_blocks, assets, markdown_base)

        safe_turn = dict(turn)
        # build_turns() deliberately excludes hyperlink sentinels from
        # source_orders. Prevent the base compatibility implementation from
        # reintroducing every block in first_order..last_order.
        safe_turn["first_order"] = None
        safe_turn["last_order"] = None
        return original(safe_turn, source_blocks, assets, markdown_base)

    return wrapped


def _with_v10_semantic_renderer(function, *args, **kwargs):
    previous_source_renderer = _base._source_block_markdown
    previous_turn_body = _base._turn_body
    previous_version = _base.CANONICAL_LEGACY_DOCX_VERSION
    previous_inline_renderer = _docx_renderer.add_inline_content

    _base._source_block_markdown = source_block_markdown
    _base._turn_body = _turn_body_without_range_expansion(previous_turn_body)
    _base.CANONICAL_LEGACY_DOCX_VERSION = CANONICAL_LEGACY_DOCX_VERSION
    _docx_renderer.add_inline_content = _add_inline_content_with_html_breaks(previous_inline_renderer)
    try:
        return function(*args, **kwargs)
    finally:
        _base._source_block_markdown = previous_source_renderer
        _base._turn_body = previous_turn_body
        _base.CANONICAL_LEGACY_DOCX_VERSION = previous_version
        _docx_renderer.add_inline_content = previous_inline_renderer


def build_legacy_markdown(
    conversation: dict[str, Any],
    *,
    source_docx: Path | None = None,
    asset_export=None,
    markdown_base: Path | None = None,
) -> str:
    return _with_v10_semantic_renderer(
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
    return _with_v10_semantic_renderer(
        _base.export_legacy_canonical_docx,
        conversation,
        output_dir,
        overwrite=overwrite,
        docx_root=docx_root,
    )
