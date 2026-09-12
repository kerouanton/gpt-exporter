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
from gpt_exporter.provider_artifacts import ManagedProviderInfo, ProviderArtifactStore
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
    managed: bool = False
    managed_distribution: str = ""
    managed_version: str = ""
    managed_sha256: str = ""
    managed_source_filename: str = ""
    managed_installed_at: str = ""

    @property
    def status_label(self) -> str:
        return self.state.value.capitalize()

    @property
    def provenance_label(self) -> str:
        return "Managed" if self.managed else "Bundled / environment"


class ProviderManager:
    """Central view of discovery, activation state and managed-artifact provenance."""

    def __init__(
        self,
        discovery: ProviderDiscoveryResult,
        *,
        settings: ProviderSettings | None = None,
        artifact_store: ProviderArtifactStore | None = None,
    ) -> None:
        self._discovery = discovery
        self.settings = settings or ProviderSettings()
        self.artifact_store = artifact_store or ProviderArtifactStore()
        self._refresh_state()

    @classmethod
    def discover(
        cls,
        *,
        include_source_packages: bool = True,
        settings_path: Path | str | None = None,
        artifact_root: Path | str | None = None,
    ) -> "ProviderManager":
        return cls(
            discover_available_providers(include_embedded=include_source_packages),
            settings=ProviderSettings(settings_path),
            artifact_store=ProviderArtifactStore(artifact_root),
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

    def managed_info(self, provider_id: str) -> ManagedProviderInfo | None:
        """Return managed artifact provenance for one provider id, if present."""
        return self._managed_by_provider.get(provider_id)

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        """Persist provider activation preference and refresh this manager snapshot."""
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
        """Reload durable settings/provenance and rebuild derived lifecycle state."""
        self._disabled_ids = self.settings.disabled_ids()
        self._managed_by_provider = self._build_managed_map(
            self.artifact_store.managed_distributions()
        )
        self._records = self._build_records(
            self._discovery,
            self._disabled_ids,
            self._managed_by_provider,
        )
        self._registry = self._build_active_registry(self._discovery, self._disabled_ids)

    @staticmethod
    def _build_managed_map(
        distributions: tuple[ManagedProviderInfo, ...],
    ) -> dict[str, ManagedProviderInfo]:
        result: dict[str, ManagedProviderInfo] = {}
        for info in distributions:
            for provider_id in info.provider_ids:
                # Duplicate managed provider IDs are diagnosed by artifact operations;
                # inventory remains deterministic and non-fatal.
                result.setdefault(provider_id, info)
        return result

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

    @staticmethod
    def _managed_fields(info: ManagedProviderInfo | None) -> dict[str, object]:
        if info is None:
            return {}
        return {
            "managed": True,
            "managed_distribution": info.distribution_name,
            "managed_version": info.version,
            "managed_sha256": info.sha256,
            "managed_source_filename": info.source_filename,
            "managed_installed_at": info.installed_at,
        }

    @classmethod
    def _build_records(
        cls,
        discovery: ProviderDiscoveryResult,
        disabled_ids: frozenset[str],
        managed_by_provider: dict[str, ManagedProviderInfo],
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
                    **cls._managed_fields(managed_by_provider.get(descriptor.provider_id)),
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
                    **cls._managed_fields(managed_by_provider.get(provider_id)),
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
