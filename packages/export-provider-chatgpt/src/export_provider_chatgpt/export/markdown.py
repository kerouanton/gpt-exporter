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
from typing import Any

from gpt_exporter.export.markdown import MarkdownExportResult
from gpt_exporter.paths import default_archive_paths


DEFAULT_ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"


@lru_cache(maxsize=1)
def _implementation() -> ModuleType:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        from . import _native_markdown
    return _native_markdown


def _is_context_stuff_message(message: Any) -> bool:
    """Return whether *message* is an internal ChatGPT file-context payload.

    ChatGPT emits ``api_tool`` messages with ``metadata.command`` set to
    ``context_stuff`` when an attached file is parsed and supplied to the
    model.  Those nodes are implementation context, not visible assistant
    messages.  Some DOCX payloads contain ``image_asset_pointer`` parts; the
    historical renderer mistook those for visible generated-image tool output
    and exported the complete parsed document into Markdown/DOCX.
    """

    if not isinstance(message, dict):
        return False
    metadata = message.get("metadata")
    return isinstance(metadata, dict) and metadata.get("command") == "context_stuff"


def _filter_context_stuff_nodes(
    active_path: list[dict[str, Any]],
    statistics: Any,
) -> list[dict[str, Any]]:
    """Remove internal file-context nodes while preserving the raw source JSON."""

    filtered: list[dict[str, Any]] = []
    for node in active_path:
        message = node.get("message") if isinstance(node, dict) else None
        if _is_context_stuff_message(message):
            statistics.skipped_reasons["context_stuff"] += 1
            continue
        filtered.append(node)
    return filtered


def _normalize_asset_metadata_from_canonical_paths(
    assets: dict[str, Any],
    asset_root: Path,
    implementation: ModuleType,
) -> None:
    """Repair stale registry kind/MIME data using the canonical bucket on disk.

    Asset migration can move a file into ``assets/image`` while an older
    registry record still says ``kind=attachment``.  Missing-DOCX regeneration
    does not run the importer migration first, so the native renderer would
    treat such an image as an attachment reference even though the physical
    path is already canonical.  The canonical bucket is authoritative here.
    """

    kind_by_bucket = {
        "attachment": "attachment",
        "dictation": "dictation",
        "image": "image",
        "external": "external_image",
    }

    for asset in assets.values():
        filename = str(getattr(asset, "filename", "") or "").replace("\\", "/")
        if not filename:
            continue
        relative = Path(filename)
        if not relative.parts:
            continue
        bucket = relative.parts[0].casefold()
        canonical_kind = kind_by_bucket.get(bucket)
        if canonical_kind is None:
            continue

        asset.kind = canonical_kind

        local_path = (asset_root / relative).resolve()
        inferred = implementation.infer_local_content_type(local_path)
        if inferred:
            asset.content_type = inferred


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
        _normalize_asset_metadata_from_canonical_paths(
            assets,
            asset_root,
            implementation,
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

    visible_path = _filter_context_stuff_nodes(active_path, statistics)
    messages = implementation.extract_visible_messages(
        active_path=visible_path,
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
