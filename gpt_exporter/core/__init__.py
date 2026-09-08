"""Provider-neutral core APIs for conversation archives.

The core package must never import a concrete provider implementation.
Providers depend on the core, never the reverse.
"""

from .model import CanonicalAsset, CanonicalConversation, CanonicalMessage
from .provider import ConversationProvider, ProviderDescriptor
from .provider_registry import ProviderRegistry

__all__ = [
    "CanonicalAsset",
    "CanonicalConversation",
    "CanonicalMessage",
    "ConversationProvider",
    "ProviderDescriptor",
    "ProviderRegistry",
]
