"""Library API for exporting ChatGPT conversations to Markdown.

This is the stable in-process boundary used by the v2.9 refactor.  The current
v2.8 implementation still lives in the historical ``export_markdown.py``
module; it is loaded lazily so importing this library module has no archive or
console side effects.  Callers use explicit paths and receive a structured
result instead of driving the legacy CLI through ``sys.argv``.
"""

from __future__ import annotations

import contextlib
import importlib
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from gpt_exporter.paths import default_archive_paths


DEFAULT_ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"


@dataclass(frozen=True, slots=True)
class MarkdownExportResult:
    """Structured result of one Markdown export."""

    output_path: Path
    debug_output_path: Path | None
    conversation_title: str
    conversation_id: str
    all_nodes: int
    active_nodes: int
    exported_messages: int
    resolved_assets: dict[str, int]
    unresolved_assets: dict[str, int]
    cleaned_marker_types: dict[str, int]


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    """Load the v2.8 implementation lazily behind the library boundary.

    The historical module prints its filename at import time.  Suppress only
    that compatibility diagnostic so the public library call remains quiet.
    The implementation itself is deliberately unchanged in this phase.
    """

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        return importlib.import_module("export_markdown")


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
    """Export one conversation file to Markdown without invoking a CLI.

    Exceptions are intentionally allowed to propagate to the caller.  CLI and
    GUI layers can therefore map failures to exit codes or dialogs without the
    library knowing about either presentation layer.
    """

    implementation = _implementation()
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()

    defaults = default_archive_paths()
    if asset_index_path is None:
        asset_index = defaults.reports / DEFAULT_ASSET_INDEX_NAME
    else:
        asset_index = Path(asset_index_path).expanduser().resolve()

    if asset_directory is None:
        asset_root = defaults.assets
    else:
        asset_root = Path(asset_directory).expanduser().resolve()

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
