"""Browser-collector integration for the Discord provider.

The provider deliberately does not read Discord tokens, cookies, passwords or local
browser profiles.  Collection runs in the user's already-authenticated Discord web
session, mirroring the established ChatGPT collector workflow.
"""

from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

EXPORT_GLOB = "discord-dm-export-v15_*.json"
EXPORTER_NAME = "9c discord-exporter"
SCHEMA_VERSION = 15

# Discord renders both Unicode and custom emoji as inline <img alt="…"> in
# message content. The historical v15 resource used textContent and therefore
# dropped those emoji. Apply a backwards-compatible source overlay when the
# collector is copied to the browser; existing v15 exports remain valid.
_SEMANTIC_CONTENT_SENTINEL = (
    '        for (const br of clone.querySelectorAll("br")) br.replaceWith("\\n");\n'
    '        return normalizeText(clone.textContent);'
)
_SEMANTIC_CONTENT_EMOJI_PATCH = (
    '        for (const image of clone.querySelectorAll("img[alt]")) {\n'
    '            const alt = normalizeText(image.getAttribute("alt"));\n'
    '            if (alt) image.replaceWith(alt);\n'
    '        }\n'
    '        for (const br of clone.querySelectorAll("br")) br.replaceWith("\\n");\n'
    '        return normalizeText(clone.textContent);'
)


@dataclass(frozen=True, slots=True)
class CollectorExport:
    path: Path
    channel_id: str
    title: str
    message_count: int
    exported_at: str | None


def collector_javascript() -> str:
    resource = files("gpt_exporter.providers.discord.resources").joinpath(
        "export_current_dm.js"
    )
    source = resource.read_text(encoding="utf-8")
    if _SEMANTIC_CONTENT_SENTINEL not in source:
        raise RuntimeError("Packaged Discord collector semanticContent function changed unexpectedly")
    return source.replace(
        _SEMANTIC_CONTENT_SENTINEL,
        _SEMANTIC_CONTENT_EMOJI_PATCH,
        1,
    )


def open_discord() -> bool:
    return bool(webbrowser.open("https://discord.com/channels/@me", new=2))


def snapshot_exports(download_directory: Path) -> set[Path]:
    directory = Path(download_directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Download directory does not exist: {directory}")
    return {path.resolve() for path in directory.glob(EXPORT_GLOB)}


def validate_collector_export(path: Path) -> CollectorExport:
    path = Path(path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Discord collector export root must be a JSON object")
    if payload.get("exporter") != EXPORTER_NAME:
        raise ValueError("JSON file was not produced by the 9c Discord collector")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Discord collector schema: {payload.get('schema_version')!r}"
        )

    conversation = payload.get("conversation")
    messages = payload.get("messages")
    if not isinstance(conversation, dict):
        raise ValueError("Discord collector export has no conversation object")
    if not isinstance(messages, list):
        raise ValueError("Discord collector export has no messages array")

    channel_id = str(conversation.get("channel_id") or "").strip()
    if not channel_id.isdigit():
        raise ValueError("Discord collector export has an invalid channel ID")
    if payload.get("message_count") != len(messages):
        raise ValueError(
            "Discord collector message count mismatch: "
            f"declared={payload.get('message_count')!r}, actual={len(messages)}"
        )

    ids: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Discord collector contains a non-object message")
        message_id = str(message.get("id") or "")
        if not message_id.isdigit():
            raise ValueError("Discord collector contains an invalid message ID")
        ids.append(message_id)
    if len(ids) != len(set(ids)):
        raise ValueError("Discord collector contains duplicate message IDs")

    return CollectorExport(
        path=path,
        channel_id=channel_id,
        title=str(conversation.get("title") or f"Discord DM {channel_id}"),
        message_count=len(messages),
        exported_at=(
            str(payload["exported_at"])
            if isinstance(payload.get("exported_at"), str)
            else None
        ),
    )


def wait_for_new_export(
    download_directory: Path,
    *,
    known_files: set[Path] | None = None,
    timeout_seconds: float = 7200.0,
    poll_seconds: float = 0.5,
) -> CollectorExport:
    directory = Path(download_directory).expanduser().resolve()
    known = {path.resolve() for path in (known_files or set())}
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        candidates = sorted(
            (
                path
                for path in directory.glob(EXPORT_GLOB)
                if path.resolve() not in known
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for candidate in candidates:
            try:
                return validate_collector_export(candidate)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                last_error = error
        time.sleep(poll_seconds)

    detail = f" Last validation error: {last_error}" if last_error else ""
    raise TimeoutError(f"Timed out waiting for Discord export in {directory}.{detail}")
