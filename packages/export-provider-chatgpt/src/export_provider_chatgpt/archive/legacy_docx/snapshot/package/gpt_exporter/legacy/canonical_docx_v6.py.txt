"""Legacy canonical renderer v6 with richer Word-to-Markdown preservation.

This compatibility layer keeps the proven v5 export/asset pipeline intact and
replaces only the source-block renderer. It can be folded into canonical_docx
once the real corpus validation is complete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import canonical_docx as _base
from .word_markdown import source_block_markdown


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v6"
CanonicalLegacyDocxResult = _base.CanonicalLegacyDocxResult
canonical_output_name = _base.canonical_output_name


def _with_v6_source_renderer(function, *args, **kwargs):
    previous_renderer = _base._source_block_markdown
    previous_version = _base.CANONICAL_LEGACY_DOCX_VERSION
    _base._source_block_markdown = source_block_markdown
    _base.CANONICAL_LEGACY_DOCX_VERSION = CANONICAL_LEGACY_DOCX_VERSION
    try:
        return function(*args, **kwargs)
    finally:
        _base._source_block_markdown = previous_renderer
        _base.CANONICAL_LEGACY_DOCX_VERSION = previous_version


def build_legacy_markdown(
    conversation: dict[str, Any],
    *,
    source_docx: Path | None = None,
    asset_export=None,
    markdown_base: Path | None = None,
) -> str:
    return _with_v6_source_renderer(
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
    return _with_v6_source_renderer(
        _base.export_legacy_canonical_docx,
        conversation,
        output_dir,
        overwrite=overwrite,
        docx_root=docx_root,
    )
