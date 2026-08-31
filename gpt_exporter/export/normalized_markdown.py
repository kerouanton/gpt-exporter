"""Provider-neutral Markdown rendering for normalized conversations."""

from __future__ import annotations

from datetime import datetime, timezone

from gpt_exporter.model import Conversation, Message


def _format_timestamp(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _display_author(message: Message, conversation: Conversation) -> str:
    if message.author_name.strip():
        return message.author_name.strip()
    role = message.author_role.strip()
    if role == "assistant" and conversation.provider_key == "chatgpt":
        return "ChatGPT"
    if role == "user" and conversation.provider_key == "chatgpt":
        return "Bruno"
    if role:
        return role.capitalize()
    return "Unknown"


def render_conversation_markdown(
    conversation: Conversation,
    *,
    include_timestamps: bool = False,
) -> str:
    """Render one normalized conversation without provider-native knowledge."""

    title = (conversation.title or "Untitled conversation").replace("\n", " ").strip()
    lines: list[str] = [
        f"# {title}",
        "",
        f"- Provider: `{conversation.provider_key}`",
        f"- Conversation ID: `{conversation.conversation_id}`",
        f"- Created: {_format_timestamp(conversation.created_at)}",
        f"- Updated: {_format_timestamp(conversation.updated_at)}",
        f"- Messages: {conversation.message_count}",
        "",
        "---",
        "",
    ]

    for message in conversation.messages:
        lines.append(f"## {_display_author(message, conversation)}")
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
