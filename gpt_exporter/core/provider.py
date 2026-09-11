"""Contracts implemented by concrete conversation providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from .model import CanonicalConversation


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """Stable identity and human-readable metadata for one provider."""

    provider_id: str
    display_name: str
    version: str
    api_version: int = 1
    capabilities: tuple[str, ...] = ()


@runtime_checkable
class ConversationProvider(Protocol):
    """Boundary between provider-specific ingestion and the shared core."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        ...

    def discover(self, source: Path) -> Iterable[Path]:
        """Yield provider source items below an explicit source path."""
        ...

    def normalize(self, source: Path) -> CanonicalConversation:
        """Convert one provider source item into the canonical core model."""
        ...
