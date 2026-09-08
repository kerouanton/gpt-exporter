"""Provider-neutral Markdown rendering plus a legacy ChatGPT compatibility facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from gpt_exporter.core import CanonicalAsset, CanonicalConversation


@dataclass(frozen=True, slots=True)
class MarkdownExportResult:
    """Structured result shared by canonical and compatibility Markdown exports."""

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


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _is_local_image(asset: CanonicalAsset) -> bool:
    source = (asset.source_ref or "").strip()
    if not source:
        return False
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return False
    if asset.media_type and asset.media_type.casefold().startswith("image/"):
        return True
    suffix = Path(parsed.path).suffix.casefold()
    return suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


def _is_author_avatar(asset: CanonicalAsset) -> bool:
    return str(asset.metadata.get("kind") or "").casefold() == "author-avatar"


def render_canonical_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool = False,
) -> str:
    """Render a provider-neutral canonical conversation as Markdown.

    Canonical author names take precedence over abstract roles when available.
    Remote/provider asset references remain links. Local image references are
    emitted as Markdown images so downstream DOCX renderers can embed them.
    Author avatars are a generic canonical asset kind and are shown once per
    consecutive author run, matching chat-style grouped messages.
    """

    title = conversation.title.strip() or "Untitled conversation"
    lines = [f"# {title}", ""]
    previous_author_key: tuple[str, str] | None = None
    for message in conversation.messages:
        body = message.content.strip()
        content_assets = tuple(asset for asset in message.assets if not _is_author_avatar(asset))
        avatar = next((asset for asset in message.assets if _is_author_avatar(asset)), None)
        if not body and not content_assets:
            continue
        role = (message.role or "unknown").replace("_", " ").strip().title()
        heading = (message.author_name or "").strip() or role
        author_key = (str(message.author_id or ""), heading)
        if (
            avatar
            and avatar.source_ref
            and _is_local_image(avatar)
            and author_key != previous_author_key
        ):
            label = _escape_label(f"Author avatar: {heading}")
            lines.extend([f"![{label}]({avatar.source_ref})", ""])
        lines.extend([f"## {heading}", ""])
        if include_timestamps and message.created_at:
            lines.extend([f"*Timestamp: {message.created_at}*", ""])
        if body:
            lines.extend([body, ""])
        for asset in content_assets:
            label = _escape_label(asset.name or asset.asset_id or "Attachment")
            if asset.source_ref:
                if _is_local_image(asset):
                    lines.append(f"![{label}]({asset.source_ref})")
                else:
                    lines.append(f"- [{label}]({asset.source_ref})")
            else:
                lines.append(f"- {label}")
        if content_assets:
            lines.append("")
        previous_author_key = author_key
    return "\n".join(lines).rstrip() + "\n"


def export_canonical_markdown(
    conversation: CanonicalConversation,
    output_path: Path | str,
    *,
    include_timestamps: bool = False,
) -> MarkdownExportResult:
    """Write one canonical conversation without importing any provider package."""

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_canonical_markdown(conversation, include_timestamps=include_timestamps),
        encoding="utf-8",
    )
    exported_messages = sum(
        bool(message.content.strip()) or bool(
            tuple(asset for asset in message.assets if not _is_author_avatar(asset))
        )
        for message in conversation.messages
    )
    return MarkdownExportResult(
        output_path=output,
        debug_output_path=None,
        conversation_title=conversation.title,
        conversation_id=conversation.conversation_id,
        all_nodes=len(conversation.messages),
        active_nodes=len(conversation.messages),
        exported_messages=exported_messages,
        resolved_assets={},
        unresolved_assets={},
        cleaned_marker_types={},
    )


def export_markdown(*args, **kwargs) -> MarkdownExportResult:
    """Compatibility facade for historical raw ChatGPT JSON/XZ callers."""

    from gpt_exporter.providers.gpt.export.markdown import export_markdown as provider_export

    return provider_export(*args, **kwargs)


__all__ = [
    "MarkdownExportResult",
    "export_canonical_markdown",
    "export_markdown",
    "render_canonical_markdown",
]
