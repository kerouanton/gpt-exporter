"""Provider-neutral Markdown rendering plus a legacy ChatGPT compatibility facade."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gpt_exporter.core import CanonicalConversation


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


def render_canonical_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool = False,
) -> str:
    """Render a provider-neutral canonical conversation as Markdown."""

    title = conversation.title.strip() or "Untitled conversation"
    lines = [f"# {title}", ""]
    for message in conversation.messages:
        body = message.content.strip()
        if not body:
            continue
        role = (message.role or "unknown").replace("_", " ").strip().title()
        lines.extend([f"## {role}", ""])
        if include_timestamps and message.created_at:
            lines.extend([f"*Timestamp: {message.created_at}*", ""])
        lines.extend([body, ""])
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
        render_canonical_markdown(
            conversation,
            include_timestamps=include_timestamps,
        ),
        encoding="utf-8",
    )
    exported_messages = sum(bool(message.content.strip()) for message in conversation.messages)
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
