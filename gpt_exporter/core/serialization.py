"""Portable serialization for provider-neutral canonical conversations."""

from __future__ import annotations

import json
import lzma
from pathlib import Path
from typing import Any

from .model import CanonicalAsset, CanonicalConversation, CanonicalMessage


CANONICAL_SCHEMA = "gpt-exporter-canonical-conversation-v1"


def _asset_to_dict(asset: CanonicalAsset) -> dict[str, Any]:
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "media_type": asset.media_type,
        "source_ref": asset.source_ref,
        "metadata": dict(asset.metadata),
    }


def _message_to_dict(message: CanonicalMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "role": message.role,
        "content": message.content,
        "created_at": message.created_at,
        "author_id": message.author_id,
        "author_name": message.author_name,
        "assets": [_asset_to_dict(asset) for asset in message.assets],
        "metadata": dict(message.metadata),
    }


def conversation_to_dict(conversation: CanonicalConversation) -> dict[str, Any]:
    return {
        "schema": CANONICAL_SCHEMA,
        "conversation_id": conversation.conversation_id,
        "provider_id": conversation.provider_id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "category_hints": list(conversation.category_hints),
        "messages": [_message_to_dict(message) for message in conversation.messages],
        "metadata": dict(conversation.metadata),
    }


def _asset_from_dict(payload: dict[str, Any]) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=str(payload.get("asset_id") or ""),
        name=str(payload.get("name") or ""),
        media_type=(str(payload["media_type"]) if payload.get("media_type") is not None else None),
        source_ref=(str(payload["source_ref"]) if payload.get("source_ref") is not None else None),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


def _message_from_dict(payload: dict[str, Any]) -> CanonicalMessage:
    raw_assets = payload.get("assets")
    assets = tuple(
        _asset_from_dict(item)
        for item in raw_assets
        if isinstance(item, dict)
    ) if isinstance(raw_assets, list) else ()
    return CanonicalMessage(
        message_id=str(payload.get("message_id") or ""),
        role=str(payload.get("role") or "unknown"),
        content=str(payload.get("content") or ""),
        created_at=(str(payload["created_at"]) if payload.get("created_at") is not None else None),
        author_id=(str(payload["author_id"]) if payload.get("author_id") is not None else None),
        author_name=(str(payload["author_name"]) if payload.get("author_name") is not None else None),
        assets=assets,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


def conversation_from_dict(payload: dict[str, Any]) -> CanonicalConversation:
    if payload.get("schema") != CANONICAL_SCHEMA:
        raise ValueError(f"Unsupported canonical conversation schema: {payload.get('schema')!r}")
    conversation_id = str(payload.get("conversation_id") or "").strip()
    provider_id = str(payload.get("provider_id") or "").strip()
    if not conversation_id or not provider_id:
        raise ValueError("Canonical conversation requires conversation_id and provider_id")
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise ValueError("Canonical conversation requires a messages list")
    raw_hints = payload.get("category_hints")
    category_hints = tuple(
        str(item).strip() for item in raw_hints
        if isinstance(item, str) and item.strip()
    ) if isinstance(raw_hints, list) else ()
    return CanonicalConversation(
        conversation_id=conversation_id,
        provider_id=provider_id,
        title=str(payload.get("title") or "Untitled conversation"),
        messages=tuple(_message_from_dict(item) for item in raw_messages if isinstance(item, dict)),
        created_at=(str(payload["created_at"]) if payload.get("created_at") is not None else None),
        updated_at=(str(payload["updated_at"]) if payload.get("updated_at") is not None else None),
        category_hints=category_hints,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


def read_json_payload(path: Path) -> object:
    path = Path(path)
    if path.name.endswith(".xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def write_canonical_conversation(path: Path, conversation: CanonicalConversation) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(conversation_to_dict(conversation), ensure_ascii=False, indent=2) + "\n"
    if path.name.endswith(".xz"):
        with lzma.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    else:
        path.write_text(text, encoding="utf-8")


def read_canonical_conversation(path: Path) -> CanonicalConversation:
    payload = read_json_payload(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected canonical conversation object: {path}")
    return conversation_from_dict(payload)


def try_read_canonical_conversation(path: Path) -> CanonicalConversation | None:
    payload = read_json_payload(path)
    if not is_canonical_payload(payload):
        return None
    assert isinstance(payload, dict)
    return conversation_from_dict(payload)


def is_canonical_payload(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("schema") == CANONICAL_SCHEMA
