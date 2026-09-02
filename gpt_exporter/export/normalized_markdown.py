"""Provider-neutral Markdown rendering for normalized conversations."""

from __future__ import annotations

from datetime import datetime

from gpt_exporter.model import Conversation, Message


def _format_timestamp(value: datetime | None) -> str:
    """Match the historical exporter timestamp presentation exactly."""
    if value is None:
        return "unknown"
    try:
        return value.astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, TypeError, ValueError):
        return f"invalid timestamp: {value!r}"


def _display_author(message: Message) -> str:
    if message.author_name.strip():
        return message.author_name.strip()
    role = message.author_role.strip()
    if role:
        return role.capitalize()
    return "Unknown"


def render_conversation_markdown(
    conversation: Conversation,
    *,
    include_timestamps: bool = False,
) -> str:
    """Render the provider-defined visible projection using the stable archive format."""

    title = (conversation.title or "Untitled conversation").replace("\n", " ").strip()
    lines: list[str] = [
        f"# {title}",
        "",
        f"- Conversation ID: `{conversation.conversation_id}`",
        f"- Created: {_format_timestamp(conversation.created_at)}",
        f"- Updated: {_format_timestamp(conversation.updated_at)}",
        f"- Messages: {conversation.visible_message_count}",
        "",
        "---",
        "",
    ]

    for message in conversation.visible_messages:
        lines.append(f"## {_display_author(message)}")
        lines.append("")
        if include_timestamps:
            lines.append(f"*{_format_timestamp(message.created_at)}*")
            lines.append("")
        lines.append(message.text)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_conversation_markdown"]
