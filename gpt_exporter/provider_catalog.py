"""Read-only provider catalog contract for Stage D discovery and updates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from gpt_exporter.core.provider_discovery import PROVIDER_API_VERSION
from gpt_exporter.provider_artifacts import canonical_distribution_name

_CATALOG_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _parse_version(value: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Catalog version must use MAJOR.MINOR.PATCH: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _require_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Catalog artifact URL must use HTTPS: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class ProviderCatalogEntry:
    """Latest catalog metadata advertised for one provider."""

    provider_id: str
    display_name: str
    distribution_name: str
    version: str
    provider_api_version: int
    min_msne_version: str
    artifact_url: str
    sha256: str
    capabilities: tuple[str, ...] = ()
    description: str = ""

    @property
    def version_key(self) -> tuple[int, int, int]:
        return _parse_version(self.version)

    @property
    def min_msne_version_key(self) -> tuple[int, int, int]:
        return _parse_version(self.min_msne_version)

    @property
    def compatible_provider_api(self) -> bool:
        return self.provider_api_version == PROVIDER_API_VERSION

    def supports_msne(self, version: str) -> bool:
        """Return whether this release supports the supplied MSNE host version."""
        return _parse_version(version) >= self.min_msne_version_key

    def is_update_for(self, installed_version: str | None) -> bool:
        if not installed_version:
            return False
        return self.version_key > _parse_version(installed_version)


@dataclass(frozen=True, slots=True)
class ProviderCatalog:
    """Validated provider catalog snapshot."""

    catalog_id: str
    generated_at: str
    entries: tuple[ProviderCatalogEntry, ...]

    @classmethod
    def from_json_text(cls, text: str) -> "ProviderCatalog":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError("Provider catalog is not valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("Provider catalog root must be an object")
        try:
            schema_version = int(payload.get("schema_version", 0))
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid provider catalog schema version") from error
        if schema_version != _CATALOG_SCHEMA_VERSION:
            raise ValueError("Unsupported provider catalog schema version")
        catalog_id = str(payload.get("catalog_id", "")).strip()
        generated_at = str(payload.get("generated_at", "")).strip()
        if not catalog_id or not generated_at:
            raise ValueError("Provider catalog must define catalog_id and generated_at")
        raw_entries = payload.get("providers")
        if not isinstance(raw_entries, list):
            raise ValueError("Provider catalog providers must be a list")

        entries: list[ProviderCatalogEntry] = []
        seen_provider_ids: set[str] = set()
        seen_distributions: set[str] = set()
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ValueError("Provider catalog entry must be an object")
            provider_id = str(raw.get("provider_id", "")).strip()
            display_name = str(raw.get("display_name", "")).strip()
            distribution_name = str(raw.get("distribution_name", "")).strip()
            version = str(raw.get("version", "")).strip()
            min_msne_version = str(raw.get("min_msne_version", "")).strip()
            artifact_url = str(raw.get("artifact_url", "")).strip()
            sha256 = str(raw.get("sha256", "")).strip().lower()
            description = str(raw.get("description", "")).strip()
            try:
                provider_api_version = int(raw.get("provider_api_version"))
            except (TypeError, ValueError) as error:
                raise ValueError(f"Provider {provider_id!r} has invalid provider_api_version") from error
            raw_capabilities = raw.get("capabilities", [])
            if not isinstance(raw_capabilities, list) or not all(
                isinstance(item, str) and item.strip() for item in raw_capabilities
            ):
                raise ValueError(f"Provider {provider_id!r} has invalid capabilities")
            capabilities = tuple(item.strip() for item in raw_capabilities)

            if not _PROVIDER_ID_RE.fullmatch(provider_id):
                raise ValueError(f"Invalid catalog provider_id: {provider_id!r}")
            if not display_name:
                raise ValueError(f"Provider {provider_id!r} has no display_name")
            canonical_distribution_name(distribution_name)
            _parse_version(version)
            _parse_version(min_msne_version)
            _require_https_url(artifact_url)
            if not _SHA256_RE.fullmatch(sha256):
                raise ValueError(f"Provider {provider_id!r} has invalid SHA-256")
            distribution_key = canonical_distribution_name(distribution_name)
            if provider_id in seen_provider_ids:
                raise ValueError(f"Duplicate catalog provider_id: {provider_id!r}")
            if distribution_key in seen_distributions:
                raise ValueError(f"Duplicate catalog distribution: {distribution_name!r}")
            seen_provider_ids.add(provider_id)
            seen_distributions.add(distribution_key)
            entries.append(
                ProviderCatalogEntry(
                    provider_id=provider_id,
                    display_name=display_name,
                    distribution_name=distribution_name,
                    version=version,
                    provider_api_version=provider_api_version,
                    min_msne_version=min_msne_version,
                    artifact_url=artifact_url,
                    sha256=sha256,
                    capabilities=capabilities,
                    description=description,
                )
            )
        entries.sort(key=lambda item: (item.display_name.casefold(), item.provider_id))
        return cls(catalog_id=catalog_id, generated_at=generated_at, entries=tuple(entries))

    @classmethod
    def from_file(cls, path: Path | str) -> "ProviderCatalog":
        return cls.from_json_text(Path(path).read_text(encoding="utf-8"))

    def by_provider_id(self) -> dict[str, ProviderCatalogEntry]:
        return {entry.provider_id: entry for entry in self.entries}


__all__ = ["ProviderCatalog", "ProviderCatalogEntry"]
