"""Canonical provider-neutral conversation model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CanonicalAsset:
    """One provider asset normalized for the shared archive engine."""

    asset_id: str
    name: str
    media_type: str | None = None
    source_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalMessage:
    """One normalized message independent from any provider schema."""

    message_id: str
    role: str
    content: str
    created_at: str | None = None
    author_id: str | None = None
    author_name: str | None = None
    assets: tuple[CanonicalAsset, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CanonicalConversation:
    """Conversation accepted by the shared index/export engine."""

    conversation_id: str
    provider_id: str
    title: str
    messages: tuple[CanonicalMessage, ...]
    created_at: str | None = None
    updated_at: str | None = None
    category_hints: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
