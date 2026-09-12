"""Provider inventory and lifecycle state model for MSNE."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
)
from gpt_exporter.provider_loader import discover_available_providers
from gpt_exporter.provider_settings import ProviderSettings


class ProviderState(str, Enum):
    """Current runtime state of one provider candidate."""

    ENABLED = "enabled"
    DISABLED = "disabled"
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
    """Central view of provider discovery plus durable enable/disable state.

    Artifact installation/removal remains a later Stage C step. Disabling a provider
    removes it from the active registry on the next application discovery while
    preserving the installed provider package and its archive data. Zero active
    providers is a valid recoverable state handled by the application shell.
    """

    def __init__(
        self,
        discovery: ProviderDiscoveryResult,
        *,
        settings: ProviderSettings | None = None,
    ) -> None:
        self._discovery = discovery
        self.settings = settings or ProviderSettings()
        self._refresh_state()

    @classmethod
    def discover(
        cls,
        *,
        include_source_packages: bool = True,
        settings_path: Path | str | None = None,
    ) -> "ProviderManager":
        return cls(
            discover_available_providers(include_embedded=include_source_packages),
            settings=ProviderSettings(settings_path),
        )

    @property
    def registry(self) -> ProviderRegistry:
        """Return only providers currently enabled for application composition."""
        return self._registry

    @property
    def discovered_registry(self) -> ProviderRegistry:
        """Return every successfully loaded provider, including disabled providers."""
        return self._discovery.registry

    @property
    def failures(self) -> tuple[ProviderDiscoveryFailure, ...]:
        return self._discovery.failures

    def records(self) -> tuple[ProviderRecord, ...]:
        return self._records

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        """Persist provider activation preference and refresh this manager snapshot.

        All healthy providers may be disabled. The shared application treats the
        resulting empty active registry as a recovery/management state rather than
        as a fatal startup error.
        """
        provider_id = provider_id.strip()
        record = next(
            (
                item
                for item in self._records
                if item.provider_id == provider_id
                and item.discovered
                and item.state in {ProviderState.ENABLED, ProviderState.DISABLED}
            ),
            None,
        )
        if record is None:
            if any(item.provider_id == provider_id for item in self._records):
                raise ValueError(
                    f"Provider '{provider_id}' cannot be enabled or disabled in its current state"
                )
            raise KeyError(f"unknown provider: {provider_id}")

        self.settings.set_enabled(provider_id, enabled)
        self._refresh_state()

    def _refresh_state(self) -> None:
        """Reload durable activation settings and rebuild derived lifecycle state."""
        self._disabled_ids = self.settings.disabled_ids()
        self._records = self._build_records(self._discovery, self._disabled_ids)
        self._registry = self._build_active_registry(self._discovery, self._disabled_ids)

    @staticmethod
    def _failure_state(failure: ProviderDiscoveryFailure) -> ProviderState:
        text = failure.error.casefold()
        if "incompatible" in text and "api version" in text:
            return ProviderState.INCOMPATIBLE
        return ProviderState.BROKEN

    @staticmethod
    def _build_active_registry(
        discovery: ProviderDiscoveryResult,
        disabled_ids: frozenset[str],
    ) -> ProviderRegistry:
        return ProviderRegistry(
            provider
            for provider in discovery.registry.providers()
            if provider.descriptor.provider_id not in disabled_ids
        )

    @classmethod
    def _build_records(
        cls,
        discovery: ProviderDiscoveryResult,
        disabled_ids: frozenset[str],
    ) -> tuple[ProviderRecord, ...]:
        records: list[ProviderRecord] = []
        for provider in discovery.registry.providers():
            descriptor = provider.descriptor
            state = (
                ProviderState.DISABLED
                if descriptor.provider_id in disabled_ids
                else ProviderState.ENABLED
            )
            records.append(
                ProviderRecord(
                    provider_id=descriptor.provider_id,
                    display_name=descriptor.display_name,
                    version=descriptor.version,
                    api_version=int(getattr(descriptor, "api_version", PROVIDER_API_VERSION)),
                    capabilities=tuple(descriptor.capabilities),
                    state=state,
                )
            )

        for failure in discovery.failures:
            provider_id = failure.provider_id or failure.name
            display_name = failure.display_name or provider_id
            records.append(
                ProviderRecord(
                    provider_id=provider_id,
                    display_name=display_name,
                    version=failure.version,
                    api_version=failure.api_version,
                    capabilities=tuple(failure.capabilities),
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
