"""Dynamic discovery of independently installed conversation providers."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Callable, Iterable

from .provider import ConversationProvider
from .provider_registry import ProviderRegistry

PROVIDER_API_VERSION = 1
PROVIDER_ENTRY_POINT_GROUP = "gpt_exporter.provider_plugins"


@dataclass(frozen=True, slots=True)
class ProviderDiscoveryFailure:
    """One provider entry point that could not be loaded or validated."""

    name: str
    value: str
    error: str
    provider_id: str = ""
    display_name: str = ""
    version: str = ""
    api_version: int | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderDiscoveryResult:
    """Discovered providers plus non-fatal plugin loading failures."""

    registry: ProviderRegistry
    failures: tuple[ProviderDiscoveryFailure, ...] = ()


def _instantiate_provider(candidate):
    """Accept an entry point exposing either a provider instance or zero-arg factory/class."""

    if isinstance(candidate, type):
        candidate = candidate()
    elif not isinstance(candidate, ConversationProvider) and callable(candidate):
        candidate = candidate()
    if not isinstance(candidate, ConversationProvider):
        raise TypeError("entry point did not produce a ConversationProvider")
    return candidate


def _entry_points_for_group(entry_points: Callable[[], object]) -> Iterable[object]:
    discovered = entry_points()
    if hasattr(discovered, "select"):
        return discovered.select(group=PROVIDER_ENTRY_POINT_GROUP)
    if isinstance(discovered, dict):
        return discovered.get(PROVIDER_ENTRY_POINT_GROUP, ())
    return tuple(
        item
        for item in discovered
        if getattr(item, "group", None) == PROVIDER_ENTRY_POINT_GROUP
    )


def discover_providers(
    *,
    entry_points: Callable[[], object] = metadata.entry_points,
) -> ProviderDiscoveryResult:
    """Discover provider entry points without importing any concrete provider in core.

    Broken or incompatible providers are reported as failures instead of preventing
    the application from starting. Duplicate provider IDs are rejected by the
    provider-neutral registry and reported the same way. If a provider was loaded
    far enough to expose its descriptor, that metadata is retained on the failure
    record so diagnostics can report the provider's own identity and API version.
    """

    registry = ProviderRegistry()
    failures: list[ProviderDiscoveryFailure] = []

    entries = sorted(
        _entry_points_for_group(entry_points),
        key=lambda item: (str(getattr(item, "name", "")).casefold(), str(getattr(item, "value", ""))),
    )
    for entry in entries:
        name = str(getattr(entry, "name", "") or "<unnamed>")
        value = str(getattr(entry, "value", "") or "<unknown>")
        provider_id = ""
        display_name = ""
        provider_version = ""
        api_version: int | None = None
        capabilities: tuple[str, ...] = ()
        try:
            provider = _instantiate_provider(entry.load())
            descriptor = provider.descriptor
            provider_id = str(descriptor.provider_id)
            display_name = str(descriptor.display_name)
            provider_version = str(descriptor.version)
            api_version = int(getattr(descriptor, "api_version", PROVIDER_API_VERSION))
            capabilities = tuple(descriptor.capabilities)
            if api_version != PROVIDER_API_VERSION:
                raise ValueError(
                    f"provider API version {api_version} is incompatible with core API version {PROVIDER_API_VERSION}"
                )
            registry.register(provider)
        except Exception as error:  # plugin failures must not prevent core startup
            failures.append(
                ProviderDiscoveryFailure(
                    name=name,
                    value=value,
                    error=f"{type(error).__name__}: {error}",
                    provider_id=provider_id,
                    display_name=display_name,
                    version=provider_version,
                    api_version=api_version,
                    capabilities=capabilities,
                )
            )

    return ProviderDiscoveryResult(registry=registry, failures=tuple(failures))


__all__ = [
    "PROVIDER_API_VERSION",
    "PROVIDER_ENTRY_POINT_GROUP",
    "ProviderDiscoveryFailure",
    "ProviderDiscoveryResult",
    "discover_providers",
]
