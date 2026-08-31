"""ChatGPT normalization adapter with historical asset-resolution semantics.

The generic CORE renderer must not know about ChatGPT's asset registry.  This
provider-side adapter augments the common ChatGPT normalizer by rebuilding only
the display projection with the frozen v2.8 ``asset index + local fallback``
resolution rules.
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import replace
from pathlib import Path

from gpt_exporter.model import ContentBlock, Conversation

from .chatgpt_normalizer import normalize_conversation_file

with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.export import _legacy_markdown as legacy


DEFAULT_ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"


def normalize_chatgpt_conversation(
    input_path: Path | str,
    *,
    asset_directory: Path | str | None = None,
    markdown_directory: Path | str | None = None,
    asset_index_path: Path | str | None = None,
) -> Conversation:
    """Return the common model with exact historical ChatGPT asset rendering."""

    source = Path(input_path).expanduser().resolve()
    archive_root = source.parent.parent
    assets_root = (
        Path(asset_directory).expanduser().resolve()
        if asset_directory is not None
        else archive_root / "assets"
    )
    markdown_root = (
        Path(markdown_directory).expanduser().resolve()
        if markdown_directory is not None
        else archive_root / "markdown"
    )
    asset_index = (
        Path(asset_index_path).expanduser().resolve()
        if asset_index_path is not None
        else archive_root / "reports" / DEFAULT_ASSET_INDEX_NAME
    )

    base = normalize_conversation_file(
        source,
        asset_directory=assets_root,
        markdown_directory=markdown_root,
    )

    indexed_assets = legacy.load_asset_index(asset_index)
    local_assets = legacy.discover_local_assets(assets_root)
    assets = legacy.merge_asset_sources(indexed_assets, local_assets, assets_root)

    data = legacy.load_json(source)
    active_path = legacy.reconstruct_active_path(data["mapping"], data["current_node"])
    statistics = legacy.ExportStatistics()
    visible = legacy.extract_visible_messages(
        active_path=active_path,
        statistics=statistics,
        assets=assets,
        asset_directory=assets_root,
        markdown_directory=markdown_root,
    )
    display_by_node = {message.node_id: message for message in visible}

    messages = []
    for message in base.messages:
        chatgpt_metadata = message.metadata.get("chatgpt", {})
        node_id = (
            chatgpt_metadata.get("display_node_id")
            if isinstance(chatgpt_metadata, dict)
            else None
        )
        rendered = display_by_node.get(node_id)
        if rendered is None:
            messages.append(message)
            continue
        text = str(rendered.text or "")
        messages.append(
            replace(
                message,
                text=text,
                content=(ContentBlock(kind=str(rendered.content_type), text=text),),
            )
        )

    metadata = dict(base.metadata)
    native = dict(metadata.get("chatgpt", {}))
    native["export_statistics"] = {
        "exported_messages": statistics.exported_messages,
        "skipped_reasons": dict(statistics.skipped_reasons),
        "resolved_assets": dict(statistics.resolved_assets),
        "unresolved_assets": dict(statistics.unresolved_assets),
        "cleaned_marker_types": dict(statistics.cleaned_marker_types),
    }
    metadata["chatgpt"] = native

    return replace(base, messages=tuple(messages), metadata=metadata)


__all__ = ["normalize_chatgpt_conversation"]
