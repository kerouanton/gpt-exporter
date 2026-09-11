"""Provider-neutral registry for conversation providers."""

from __future__ import annotations

from collections.abc import Iterable

from .provider import ConversationProvider, ProviderDescriptor


class ProviderRegistry:
    """Keep concrete providers behind the shared provider contract.

    The registry deliberately imports no concrete provider package. Application
    composition code decides which providers are registered.
    """

    def __init__(self, providers: Iterable[ConversationProvider] = ()) -> None:
        self._providers: dict[str, ConversationProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ConversationProvider) -> None:
        descriptor = provider.descriptor
        provider_id = descriptor.provider_id.strip()
        if not provider_id:
            raise ValueError("provider_id must not be empty")
        if provider_id in self._providers:
            raise ValueError(f"provider already registered: {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> ConversationProvider:
        try:
            return self._providers[provider_id]
        except KeyError as error:
            raise KeyError(f"unknown provider: {provider_id}") from error

    def providers(self) -> tuple[ConversationProvider, ...]:
        """Return providers in stable display order for shared composition code."""
        return tuple(
            sorted(
                self._providers.values(),
                key=lambda item: (item.descriptor.display_name.casefold(), item.descriptor.provider_id),
            )
        )

    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        return tuple(provider.descriptor for provider in self.providers())

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(descriptor.provider_id for descriptor in self.descriptors())

    def __len__(self) -> int:
        return len(self._providers)
