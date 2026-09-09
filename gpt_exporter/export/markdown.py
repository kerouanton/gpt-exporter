"""Provider-neutral Markdown rendering plus a legacy ChatGPT compatibility facade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gpt_exporter.core import CanonicalAsset, CanonicalConversation


@dataclass(frozen=True, slots=True)
class MarkdownExportResult:
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
    return Path(parsed.path).suffix.casefold() in {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"
    }


def _asset_kind(asset: CanonicalAsset) -> str:
    return str(asset.metadata.get("kind") or "").casefold()


def _is_author_avatar(asset: CanonicalAsset) -> bool:
    return _asset_kind(asset) == "author-avatar"


def _render_asset(lines: list[str], asset: CanonicalAsset) -> None:
    label = _escape_label(asset.name or asset.asset_id or "Attachment")
    if asset.source_ref:
        if _is_local_image(asset):
            lines.append(f"![{label}]({asset.source_ref})")
        else:
            lines.append(f"- [{label}]({asset.source_ref})")
    else:
        lines.append(f"- {label}")


def _parse_timestamp(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        try:
            parsed = parsed.astimezone()
        except (OSError, ValueError):
            pass
    return parsed


def _date_label(value: str | None) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is not None:
        return parsed.date().isoformat()
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else None


def _time_label(value: str | None) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is not None:
        return parsed.strftime("%H:%M")
    text = str(value or "").strip()
    return text[11:16] if len(text) >= 16 else text or None


def _preserve_line_breaks(text: str) -> str:
    lines = text.split("\n")
    if len(lines) <= 1:
        return text
    rendered: list[str] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        is_fence = stripped.startswith("```") or stripped.startswith("~~~")
        current_in_fence = in_fence
        if is_fence:
            in_fence = not in_fence
        next_line = lines[index + 1] if index + 1 < len(lines) else None
        if next_line is not None and line and next_line and not current_in_fence and not is_fence:
            rendered.append(line + "  ")
        else:
            rendered.append(line)
    return "\n".join(rendered)


def _reaction_text(metadata: dict[str, Any]) -> str | None:
    raw = metadata.get("reactions")
    if not isinstance(raw, list):
        return None
    parts: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("emoji") or item.get("name") or "").strip()
        if not label:
            continue
        count = item.get("count")
        parts.append(f"{label} {count}" if isinstance(count, int) and count > 0 else label)
    return "   ".join(parts) or None


def _append_reply(lines: list[str], metadata: dict[str, Any]) -> None:
    reply = metadata.get("reply")
    if not isinstance(reply, dict):
        return
    author = str(reply.get("author") or "").strip()
    text = str(reply.get("text") or "").strip()
    url = str(reply.get("url") or "").strip()
    label = f"↪ **{author}**" if author else "↪ Reply"
    if url:
        label = f"[{label}]({url})"
    lines.append(f"> {label}")
    for part in text.splitlines():
        lines.append(f"> {part}")
    lines.append("")


def _append_preview(lines: list[str], preview: dict[str, Any], asset: CanonicalAsset | None) -> None:
    site = str(preview.get("site_name") or "").strip()
    title = str(preview.get("title") or "").strip()
    description = str(preview.get("description") or "").strip()
    url = str(preview.get("url") or "").strip()
    if site:
        lines.append(f"> **{site}**")
    if title:
        lines.append(f"> [{title}]({url})" if url else f"> **{title}**")
    elif url:
        lines.append(f"> {url}")
    for part in description.splitlines():
        lines.append(f"> {part}")
    if site or title or description or url:
        lines.append("")
    if asset is not None:
        _render_asset(lines, asset)
        lines.append("")


def _render_standard_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool,
    include_title: bool,
) -> str:
    title = conversation.title.strip() or "Untitled conversation"
    lines = [f"# {title}", ""] if include_title else []
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
        if avatar and avatar.source_ref and _is_local_image(avatar) and author_key != previous_author_key:
            label = _escape_label(f"Author avatar: {heading}")
            lines.extend([f"![{label}]({avatar.source_ref})", ""])
        lines.extend([f"## {heading}", ""])
        if include_timestamps and message.created_at:
            lines.extend([f"*Timestamp: {message.created_at}*", ""])
        if body:
            lines.extend([body, ""])
        for asset in content_assets:
            _render_asset(lines, asset)
        if content_assets:
            lines.append("")
        previous_author_key = author_key
    return "\n".join(lines).rstrip() + "\n"


def _render_chat_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool,
    include_title: bool,
) -> str:
    title = conversation.title.strip() or "Untitled conversation"
    lines = [f"# {title}", ""] if include_title else []
    previous_author_key: tuple[str, str] | None = None
    previous_date: str | None = None

    for message in conversation.messages:
        metadata = dict(message.metadata)
        body = message.content.strip()
        if metadata.get("preserve_line_breaks") and body:
            body = _preserve_line_breaks(body)
        content_assets = tuple(asset for asset in message.assets if not _is_author_avatar(asset))
        avatar = next((asset for asset in message.assets if _is_author_avatar(asset)), None)
        if not body and not content_assets and not metadata.get("reactions"):
            continue

        role = (message.role or "unknown").replace("_", " ").strip().title()
        heading = (message.author_name or "").strip() or role
        author_key = (str(message.author_id or ""), heading)
        current_date = _date_label(message.created_at)
        date_changed = bool(current_date and current_date != previous_date)
        if date_changed:
            if lines:
                lines.extend(["---", ""])
            lines.extend([f"**{current_date}**", ""])
            previous_author_key = None

        new_author_group = author_key != previous_author_key
        if avatar and avatar.source_ref and _is_local_image(avatar) and new_author_group:
            label = _escape_label(f"Author avatar: {heading}")
            lines.extend([f"![{label}]({avatar.source_ref})", ""])

        time_text = _time_label(message.created_at) if include_timestamps else ""
        if metadata.get("edited"):
            time_text = f"{time_text} · edited" if time_text else "edited"
        if new_author_group:
            header = f"**{heading}**"
            if time_text:
                header += f"  *{time_text}*"
            lines.extend([header, ""])
        elif time_text:
            lines.extend([f"*{time_text}*", ""])

        _append_reply(lines, metadata)
        if body:
            lines.extend([body, ""])

        preview_assets = [asset for asset in content_assets if _asset_kind(asset) == "external-preview"]
        raw_previews = metadata.get("link_previews")
        if isinstance(raw_previews, list):
            for index, preview in enumerate(raw_previews):
                if isinstance(preview, dict):
                    _append_preview(
                        lines,
                        preview,
                        preview_assets[index] if index < len(preview_assets) else None,
                    )

        preview_asset_ids = {id(asset) for asset in preview_assets}
        for asset in content_assets:
            if id(asset) not in preview_asset_ids:
                _render_asset(lines, asset)
        if content_assets:
            lines.append("")

        reactions = _reaction_text(metadata)
        if reactions:
            lines.extend([f"*{reactions}*", ""])

        previous_author_key = author_key
        if current_date:
            previous_date = current_date

    return "\n".join(lines).rstrip() + "\n"


def _uses_chat_semantics(conversation: CanonicalConversation) -> bool:
    """Detect an explicitly normalized chat conversation without provider checks."""
    return any(
        bool(message.metadata.get("preserve_line_breaks"))
        for message in conversation.messages
    )


def render_canonical_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool = False,
    include_title: bool = True,
    chat_style: bool | None = None,
) -> str:
    if chat_style is None:
        chat_style = _uses_chat_semantics(conversation)
    renderer = _render_chat_markdown if chat_style else _render_standard_markdown
    return renderer(
        conversation,
        include_timestamps=include_timestamps,
        include_title=include_title,
    )


def export_canonical_markdown(
    conversation: CanonicalConversation,
    output_path: Path | str,
    *,
    include_timestamps: bool = False,
    include_title: bool = True,
    chat_style: bool | None = None,
) -> MarkdownExportResult:
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_canonical_markdown(
            conversation,
            include_timestamps=include_timestamps,
            include_title=include_title,
            chat_style=chat_style,
        ),
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
    from gpt_exporter.providers.gpt.export.markdown import export_markdown as provider_export
    return provider_export(*args, **kwargs)


__all__ = [
    "MarkdownExportResult",
    "export_canonical_markdown",
    "export_markdown",
    "render_canonical_markdown",
]
