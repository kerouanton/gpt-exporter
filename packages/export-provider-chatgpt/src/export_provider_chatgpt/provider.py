"""ChatGPT provider adapter for the provider-neutral core model."""

from __future__ import annotations

import json
import lzma
from pathlib import Path
from typing import Any, Iterable

from gpt_exporter.core import (
    CanonicalConversation,
    CanonicalMessage,
    ProviderDescriptor,
)


_DESCRIPTOR = ProviderDescriptor(
    provider_id="gpt",
    display_name="ChatGPT",
    version="1",
)
_EXCLUDED_CONTENT_TYPES = {
    "user_editable_context",
    "model_editable_context",
    "thoughts",
    "reasoning_recap",
}
_VISIBLE_ROLES = {"user", "assistant"}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (_normalize_text(item) for item in value))).strip()
    if isinstance(value, dict):
        if "text" in value:
            return _normalize_text(value["text"])
        if "parts" in value:
            return _normalize_text(value["parts"])
    return ""


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content") or {}
    return _normalize_text(content.get("text") or content.get("parts"))


def _visible_message(message: dict[str, Any]) -> bool:
    author = message.get("author") or {}
    role = author.get("role")
    if role not in _VISIBLE_ROLES:
        return False
    metadata = message.get("metadata") or {}
    if metadata.get("is_visually_hidden_from_conversation"):
        return False
    content = message.get("content") or {}
    if content.get("content_type") in _EXCLUDED_CONTENT_TYPES:
        return False
    return bool(_message_content(message))


def _read_json(path: Path) -> dict[str, Any]:
    if path.name.endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected ChatGPT conversation object: {path}")
    return payload


class ChatGPTProvider:
    """Normalize ChatGPT conversation JSON/XZ into shared core objects."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        return _DESCRIPTOR

    def discover(self, source: Path) -> Iterable[Path]:
        source = Path(source)
        if source.is_file():
            if source.name.endswith((".json", ".json.xz")):
                yield source
            return
        if not source.is_dir():
            return
        yield from sorted(source.rglob("*.json.xz"))
        for path in sorted(source.rglob("*.json")):
            if path.name != "download-index.json":
                yield path

    def normalize(self, source: Path) -> CanonicalConversation:
        source = Path(source)
        payload = _read_json(source)
        conversation_id = str(payload.get("conversation_id") or "").strip()
        if not conversation_id:
            raise ValueError(f"Missing ChatGPT conversation_id: {source}")

        messages: list[CanonicalMessage] = []
        mapping = payload.get("mapping") or {}
        if isinstance(mapping, dict):
            for node in mapping.values():
                message = node.get("message") if isinstance(node, dict) else None
                if not isinstance(message, dict) or not _visible_message(message):
                    continue
                author = message.get("author") or {}
                role = str(author.get("role") or "unknown")
                message_id = str(message.get("id") or f"{conversation_id}-{len(messages) + 1}")
                metadata = message.get("metadata")
                messages.append(
                    CanonicalMessage(
                        message_id=message_id,
                        role=role,
                        content=_message_content(message),
                        created_at=(
                            str(message.get("create_time"))
                            if message.get("create_time") is not None
                            else None
                        ),
                        author_name=(
                            str(author.get("name"))
                            if author.get("name") is not None
                            else None
                        ),
                        metadata=metadata if isinstance(metadata, dict) else {},
                    )
                )

        provider_metadata = {
            key: payload[key]
            for key in (
                "gizmo_id",
                "gizmo_type",
                "conversation_template_id",
                "conversation_origin",
                "default_model_slug",
            )
            if payload.get(key) is not None
        }
        return CanonicalConversation(
            conversation_id=conversation_id,
            provider_id=_DESCRIPTOR.provider_id,
            title=str(payload.get("title") or "Untitled"),
            messages=tuple(messages),
            created_at=(str(payload.get("create_time")) if payload.get("create_time") is not None else None),
            updated_at=(str(payload.get("update_time")) if payload.get("update_time") is not None else None),
            metadata=provider_metadata,
        )
