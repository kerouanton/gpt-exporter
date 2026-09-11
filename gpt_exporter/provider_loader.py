"""Provider discovery bridge for installed plugins and in-tree compatibility providers.

External providers are discovered through the public entry-point contract. During
this repository's migration period, provider packages that still live below
``gpt_exporter.providers`` are discovered generically by package scanning so the
application composition layer never names ChatGPT or Discord.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable

from gpt_exporter.core import ConversationProvider
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
    discover_providers,
)


def _embedded_provider_candidates() -> Iterable[tuple[str, str, object]]:
    """Yield generic plugin factories from the temporary in-tree namespace."""

    try:
        package = importlib.import_module("gpt_exporter.providers")
    except ModuleNotFoundError:
        return ()

    package_path = getattr(package, "__path__", None)
    if package_path is None:
        return ()

    result: list[tuple[str, str, object]] = []
    for item in sorted(pkgutil.iter_modules(package_path), key=lambda value: value.name.casefold()):
        if not item.ispkg:
            continue
        module_name = f"{package.__name__}.{item.name}.plugin"
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as error:
            if error.name == module_name:
                continue
            raise
        factory = getattr(module, "create_provider", None)
        if factory is not None:
            result.append((item.name, module_name, factory))
    return tuple(result)


def _instantiate(candidate: object) -> ConversationProvider:
    if isinstance(candidate, type):
        candidate = candidate()
    elif not isinstance(candidate, ConversationProvider) and callable(candidate):
        candidate = candidate()
    if not isinstance(candidate, ConversationProvider):
        raise TypeError("provider factory did not produce a ConversationProvider")
    return candidate


def discover_available_providers() -> ProviderDiscoveryResult:
    """Discover external entry points plus temporary in-tree providers.

    Entry-point providers win when an in-tree provider exposes the same stable
    provider ID. Individual plugin failures remain non-fatal.
    """

    external = discover_providers()
    registry = external.registry
    failures = list(external.failures)
    registered = set(registry.provider_ids())

    try:
        embedded = _embedded_provider_candidates()
    except Exception as error:
        failures.append(
            ProviderDiscoveryFailure(
                name="embedded",
                value="gpt_exporter.providers",
                error=f"{type(error).__name__}: {error}",
            )
        )
        embedded = ()

    for name, value, factory in embedded:
        try:
            provider = _instantiate(factory)
            descriptor = provider.descriptor
            if int(getattr(descriptor, "api_version", PROVIDER_API_VERSION)) != PROVIDER_API_VERSION:
                raise ValueError(
                    f"provider API version {descriptor.api_version} is incompatible with core API version {PROVIDER_API_VERSION}"
                )
            if descriptor.provider_id in registered:
                continue
            registry.register(provider)
            registered.add(descriptor.provider_id)
        except Exception as error:
            failures.append(
                ProviderDiscoveryFailure(
                    name=name,
                    value=value,
                    error=f"{type(error).__name__}: {error}",
                )
            )

    return ProviderDiscoveryResult(registry=registry, failures=tuple(failures))


__all__ = ["discover_available_providers"]
