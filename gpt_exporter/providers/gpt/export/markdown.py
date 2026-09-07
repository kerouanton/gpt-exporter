"""ChatGPT-native Markdown export adapter.

This preserves the historical v2.8 rendering semantics while the shared export
package exposes provider-neutral canonical rendering APIs.
"""

from __future__ import annotations

import contextlib
import io
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from gpt_exporter.export.markdown import MarkdownExportResult
from gpt_exporter.paths import default_archive_paths


DEFAULT_ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        from . import _native_markdown
    return _native_markdown


def export_markdown(
    input_path: Path | str,
    output_path: Path | str,
    *,
    asset_index_path: Path | str | None = None,
    asset_directory: Path | str | None = None,
    include_timestamps: bool = False,
    debug_output: bool = False,
    resolve_assets: bool = True,
) -> MarkdownExportResult:
    implementation = _implementation()
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()

    defaults = default_archive_paths()
    asset_index = (
        defaults.reports / DEFAULT_ASSET_INDEX_NAME
        if asset_index_path is None
        else Path(asset_index_path).expanduser().resolve()
    )
    asset_root = (
        defaults.assets
        if asset_directory is None
        else Path(asset_directory).expanduser().resolve()
    )

    statistics = implementation.ExportStatistics()

    if resolve_assets:
        indexed_assets = implementation.load_asset_index(asset_index)
        local_assets = implementation.discover_local_assets(asset_root)
        assets = implementation.merge_asset_sources(
            indexed_assets,
            local_assets,
            asset_root,
        )
    else:
        assets = {}

    data = implementation.load_json(input_path)
    mapping = data["mapping"]
    current_node_id = data["current_node"]

    statistics.all_nodes = len(mapping)
    active_path = implementation.reconstruct_active_path(
        mapping=mapping,
        current_node_id=current_node_id,
    )
    statistics.active_nodes = len(active_path)

    messages = implementation.extract_visible_messages(
        active_path=active_path,
        statistics=statistics,
        assets=assets,
        asset_directory=asset_root,
        markdown_directory=output_path.parent,
    )
    conversation = implementation.build_conversation(
        data=data,
        messages=messages,
    )
    markdown_content = implementation.build_markdown_export(
        conversation=conversation,
        include_timestamps=include_timestamps,
    )
    implementation.write_utf8_text(
        path=output_path,
        content=markdown_content,
    )

    debug_path: Path | None = None
    if debug_output:
        debug_path = output_path.with_name(output_path.stem + "-debug.txt")
        implementation.write_utf8_text(
            path=debug_path,
            content=implementation.build_debug_text_export(conversation),
        )

    return MarkdownExportResult(
        output_path=output_path,
        debug_output_path=debug_path,
        conversation_title=conversation.title,
        conversation_id=conversation.conversation_id,
        all_nodes=statistics.all_nodes,
        active_nodes=statistics.active_nodes,
        exported_messages=statistics.exported_messages,
        resolved_assets=dict(statistics.resolved_assets),
        unresolved_assets=dict(statistics.unresolved_assets),
        cleaned_marker_types=dict(statistics.cleaned_marker_types),
    )


__all__ = ["DEFAULT_ASSET_INDEX_NAME", "export_markdown"]
