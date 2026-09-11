"""Stable public SDK surface for independently packaged conversation providers."""

from __future__ import annotations

from gpt_exporter.core.model import CanonicalAsset, CanonicalConversation, CanonicalMessage
from gpt_exporter.core.provider import ConversationProvider, ProviderDescriptor
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    PROVIDER_ENTRY_POINT_GROUP,
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
    discover_providers,
)
from gpt_exporter.core.provider_registry import ProviderRegistry

__all__ = [
    "CanonicalAsset",
    "CanonicalConversation",
    "CanonicalMessage",
    "ConversationProvider",
    "PROVIDER_API_VERSION",
    "PROVIDER_ENTRY_POINT_GROUP",
    "ProviderDescriptor",
    "ProviderDiscoveryFailure",
    "ProviderDiscoveryResult",
    "ProviderRegistry",
    "discover_providers",
]
