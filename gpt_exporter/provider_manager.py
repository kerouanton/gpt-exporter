"""Read-only provider inventory and state model for MSNE.

This is the first ProviderManager stage. It centralizes provider discovery results
and exposes stable UI-facing records without yet installing, disabling, updating,
or removing provider distributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
)
from gpt_exporter.provider_loader import discover_available_providers


class ProviderState(str, Enum):
    """Current runtime state of one provider candidate."""

    ENABLED = "enabled"
    INCOMPATIBLE = "incompatible"
    BROKEN = "broken"


@dataclass(frozen=True, slots=True)
class ProviderRecord:
    """Provider metadata suitable for diagnostics and the management UI."""

    provider_id: str
    display_name: str
    version: str
    api_version: int | None
    capabilities: tuple[str, ...]
    state: ProviderState
    installed: bool = True
    discovered: bool = True
    entry_point: str = ""
    error: str = ""

    @property
    def status_label(self) -> str:
        return self.state.value.capitalize()


class ProviderManager:
    """Central read-only view of provider discovery state.

    Mutation operations deliberately do not exist yet. Later stages can add durable
    enable/disable state and artifact installation around this model without coupling
    the UI directly to ``importlib.metadata`` or provider-package internals.
    """

    def __init__(self, discovery: ProviderDiscoveryResult) -> None:
        self._discovery = discovery
        self._records = self._build_records(discovery)

    @classmethod
    def discover(cls, *, include_source_packages: bool = True) -> "ProviderManager":
        return cls(
            discover_available_providers(include_embedded=include_source_packages)
        )

    @property
    def registry(self) -> ProviderRegistry:
        return self._discovery.registry

    @property
    def failures(self) -> tuple[ProviderDiscoveryFailure, ...]:
        return self._discovery.failures

    def records(self) -> tuple[ProviderRecord, ...]:
        return self._records

    @staticmethod
    def _failure_state(failure: ProviderDiscoveryFailure) -> ProviderState:
        text = failure.error.casefold()
        if "incompatible" in text and "api version" in text:
            return ProviderState.INCOMPATIBLE
        return ProviderState.BROKEN

    @classmethod
    def _build_records(
        cls,
        discovery: ProviderDiscoveryResult,
    ) -> tuple[ProviderRecord, ...]:
        records: list[ProviderRecord] = []
        for provider in discovery.registry.providers():
            descriptor = provider.descriptor
            records.append(
                ProviderRecord(
                    provider_id=descriptor.provider_id,
                    display_name=descriptor.display_name,
                    version=descriptor.version,
                    api_version=int(getattr(descriptor, "api_version", PROVIDER_API_VERSION)),
                    capabilities=tuple(descriptor.capabilities),
                    state=ProviderState.ENABLED,
                )
            )

        for failure in discovery.failures:
            records.append(
                ProviderRecord(
                    provider_id=failure.name,
                    display_name=failure.name,
                    version="",
                    api_version=None,
                    capabilities=(),
                    state=cls._failure_state(failure),
                    discovered=False,
                    entry_point=failure.value,
                    error=failure.error,
                )
            )

        return tuple(
            sorted(
                records,
                key=lambda item: (
                    item.display_name.casefold(),
                    item.provider_id.casefold(),
                    item.state.value,
                ),
            )
        )


__all__ = ["ProviderManager", "ProviderRecord", "ProviderState"]
