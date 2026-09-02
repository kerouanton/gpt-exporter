"""Provider registry owned by exporter core."""

from __future__ import annotations

from collections.abc import Iterable

from .base import ExporterProvider


class ProviderRegistry:
    """Deterministic registry of available exporter providers."""

    def __init__(self, providers: Iterable[ExporterProvider] = ()) -> None:
        self._providers: dict[str, ExporterProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ExporterProvider) -> None:
        key = provider.key.strip().casefold()
        if not key:
            raise ValueError("Provider key cannot be empty.")
        if key in self._providers:
            raise ValueError(f"Provider already registered: {provider.key}")
        self._providers[key] = provider

    def get(self, key: str) -> ExporterProvider:
        normalized = key.strip().casefold()
        try:
            return self._providers[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown provider: {key}") from exc

    def all(self) -> tuple[ExporterProvider, ...]:
        return tuple(
            sorted(self._providers.values(), key=lambda provider: provider.display_name.casefold())
        )

    def __len__(self) -> int:
        return len(self._providers)


__all__ = ["ProviderRegistry"]
