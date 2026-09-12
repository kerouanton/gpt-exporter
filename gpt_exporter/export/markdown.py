"""Provider-neutral Markdown rendering plus a legacy ChatGPT compatibility facade."""

from __future__ import annotations

import re
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


_URL_RE = re.compile(r"(?<!<)https?://[^\s<>()]+", re.IGNORECASE)
_EMAIL_RE = re.compile(
    r"(?<![\w@])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w@])"
)
_MEDIA_ALIAS_KINDS = {"attachment", "linked-media", "external-preview"}


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
    source = str(asset.source_ref or "").strip()
    archived = bool(asset.metadata.get("local_archive_asset"))
    archive_path = str(asset.metadata.get("archive_path") or "").strip()
    kind = _asset_kind(asset)

    if source and _is_local_image(asset):
        lines.append(f"![{label}]({source})")
        return

    if archived and source and kind in {"attachment", "linked-media"}:
        lines.append(f"📎 **Archived attachment:** [{label}]({source})")
        if asset.asset_id:
            lines.append(f"  - Asset ID: `{asset.asset_id}`")
        if archive_path:
            lines.append(f"  - Archive path: `{archive_path}`")
        return

    if source:
        lines.append(f"- [{label}]({source})")
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


def _autolink_segment(segment: str) -> str:
    def url_replace(match: re.Match[str]) -> str:
        start = match.start()
        # Existing Markdown targets look like ](https://...). A naturally
        # parenthesized bare URL, (https://...), must still become clickable.
        if start >= 2 and segment[start - 2:start] == "](":
            return match.group(0)
        url = match.group(0)
        trailing = ""
        while url and url[-1] in ".,;:!?":
            trailing = url[-1] + trailing
            url = url[:-1]
        return f"<{url}>{trailing}" if url else match.group(0)

    linked = _URL_RE.sub(url_replace, segment)

    def email_replace(match: re.Match[str]) -> str:
        email = match.group(1)
        start = match.start(1)
        prefix = linked[max(0, start - 8):start].casefold()
        if prefix.endswith("mailto:") or (start > 0 and linked[start - 1] == "<"):
            return email
        if start >= 2 and linked[start - 2:start] == "](":
            return email
        return f"<{email}>"

    return _EMAIL_RE.sub(email_replace, linked)


def _autolink_plain_text(text: str) -> str:
    """Turn bare URLs and email addresses into Markdown autolinks outside code."""
    output: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        stripped = line.lstrip()
        fence = stripped.startswith("```") or stripped.startswith("~~~")
        if fence:
            output.append(line)
            in_fence = not in_fence
            continue
        if in_fence:
            output.append(line)
            continue

        parts = re.split(r"(`+[^`]*`+)", line)
        for index in range(0, len(parts), 2):
            parts[index] = _autolink_segment(parts[index])
        output.append("".join(parts))
    return "\n".join(output)


def _asset_render_name(asset: CanonicalAsset) -> str:
    name = str(asset.name or "").strip().casefold()
    if name:
        return name
    source = str(asset.source_ref or "").strip()
    return Path(urlparse(source).path).name.casefold() if source else ""


def _dedupe_content_assets(assets: tuple[CanonicalAsset, ...]) -> tuple[CanonicalAsset, ...]:
    """Collapse provider aliases while preserving distinct same-name attachments."""
    result: list[CanonicalAsset] = []
    exact_seen: set[tuple[str, str]] = set()
    seen_aliases: dict[str, set[str]] = {}

    for asset in assets:
        kind = _asset_kind(asset)
        name = _asset_render_name(asset)
        source = str(asset.source_ref or "").strip().casefold()
        exact_key = (name, source)
        if source and exact_key in exact_seen:
            continue

        previous_kinds = seen_aliases.get(name, set()) if name else set()
        if (
            name
            and kind in _MEDIA_ALIAS_KINDS
            and previous_kinds & _MEDIA_ALIAS_KINDS
            and not (kind == "attachment" and previous_kinds == {"attachment"})
        ):
            continue

        result.append(asset)
        if source:
            exact_seen.add(exact_key)
        if name and kind in _MEDIA_ALIAS_KINDS:
            seen_aliases.setdefault(name, set()).add(kind)

    return tuple(result)


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
    if description.casefold() in {"unknown", "undefined", "null"}:
        description = ""
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


def _append_timed_body(lines: list[str], time_text: str, body: str) -> None:
    """Render a compact chat line while preserving fenced-code block structure."""
    if not time_text:
        if body:
            lines.extend([body, ""])
        return
    if not body:
        lines.extend([f"**{time_text}**", ""])
        return

    stripped = body.lstrip()
    if stripped.startswith("```") or stripped.startswith("~~~"):
        lines.extend([f"**{time_text}**", "", body, ""])
        return

    body_lines = body.split("\n")
    first = body_lines[0]
    lines.append(f"**{time_text}**  {first}")
    lines.extend(body_lines[1:])
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
        body = _autolink_plain_text(message.content.strip())
        content_assets = _dedupe_content_assets(
            tuple(asset for asset in message.assets if not _is_author_avatar(asset))
        )
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


def _preview_asset_map(content_assets: tuple[CanonicalAsset, ...]) -> dict[int, CanonicalAsset]:
    result: dict[int, CanonicalAsset] = {}
    for asset in content_assets:
        if _asset_kind(asset) != "external-preview":
            continue
        index = asset.metadata.get("link_preview_index")
        if isinstance(index, int) and index >= 0 and index not in result:
            result[index] = asset
    return result


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
        if body:
            body = _autolink_plain_text(body)
        content_assets = _dedupe_content_assets(
            tuple(asset for asset in message.assets if not _is_author_avatar(asset))
        )
        avatar = next((asset for asset in message.assets if _is_author_avatar(asset)), None)
        if not body and not content_assets and not metadata.get("reactions"):
            continue

        role = (message.role or "unknown").replace("_", " ").strip().title()
        heading = (message.author_name or "").strip() or role
        author_key = (str(message.author_id or ""), heading)
        current_date = _date_label(message.created_at) if include_timestamps else None
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

        if new_author_group:
            lines.extend([f"**{heading}**", ""])

        time_text = _time_label(message.created_at) if include_timestamps else ""
        if metadata.get("edited"):
            time_text = f"{time_text} · edited" if time_text else "edited"

        has_reply = isinstance(metadata.get("reply"), dict)
        if has_reply:
            if time_text:
                lines.extend([f"**{time_text}**", ""])
            _append_reply(lines, metadata)
            if body:
                lines.extend([body, ""])
        else:
            _append_timed_body(lines, time_text or "", body)

        emitted_preview_asset_ids: set[int] = set()
        preview_assets = _preview_asset_map(content_assets)
        raw_previews = metadata.get("link_previews")
        if isinstance(raw_previews, list):
            for index, preview in enumerate(raw_previews):
                if not isinstance(preview, dict):
                    continue
                asset = preview_assets.get(index)
                _append_preview(lines, preview, asset)
                if asset is not None:
                    emitted_preview_asset_ids.add(id(asset))

        for asset in content_assets:
            if id(asset) not in emitted_preview_asset_ids:
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


def render_canonical_markdown(
    conversation: CanonicalConversation,
    *,
    include_timestamps: bool = False,
    include_title: bool = True,
    chat_style: bool = False,
) -> str:
    """Render canonical Markdown; compact chat layout is an explicit opt-in."""
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
    chat_style: bool = False,
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
    from export_provider_chatgpt.export.markdown import export_markdown as provider_export
    return provider_export(*args, **kwargs)


__all__ = [
    "MarkdownExportResult",
    "export_canonical_markdown",
    "export_markdown",
    "render_canonical_markdown",
]
