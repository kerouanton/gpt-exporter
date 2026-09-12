"""Provider discovery bridge for installed, managed and source-checkout packages.

Installed providers are discovered through the public entry-point contract. MSNE also
supports isolated per-user provider distributions and, when running directly from the
repository, generic source packages below ``packages/``. The shared application never
imports or names a concrete provider.
"""

from __future__ import annotations

import importlib
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Iterable

from gpt_exporter.core import ConversationProvider
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
    ProviderDiscoverySuccess,
    PROVIDER_ENTRY_POINT_GROUP,
    discover_providers,
)
from gpt_exporter.provider_artifacts import ProviderArtifactStore


def prepare_managed_provider_imports(
    artifact_root: Path | str | None = None,
) -> tuple[Path, ...]:
    """Expose isolated per-user provider distribution roots to Python packaging."""
    roots = ProviderArtifactStore(artifact_root).installed_roots()
    # Insert in reverse so the stable sorted order is preserved at the front of sys.path.
    for root in reversed(roots):
        root_text = str(root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
    if roots:
        importlib.invalidate_caches()
    return roots


def prepare_source_provider_imports() -> tuple[Path, ...]:
    """Expose provider distribution ``src`` roots when running from a source checkout.

    Installed applications do not need this helper because provider distributions are
    already importable through normal Python packaging. Historical compatibility
    facades use it lazily so they can resolve the extracted provider packages when a
    developer runs the repository directly without installing those distributions.
    """

    repository_root = Path(__file__).resolve().parents[1]
    packages_root = repository_root / "packages"
    if not packages_root.is_dir():
        return ()

    source_roots: list[Path] = []
    for metadata_path in sorted(packages_root.glob("*/pyproject.toml")):
        source_root = metadata_path.parent / "src"
        if not source_root.is_dir():
            continue
        source_roots.append(source_root)
        source_text = str(source_root)
        if source_text not in sys.path:
            sys.path.insert(0, source_text)
    return tuple(source_roots)


def _source_package_candidates() -> Iterable[tuple[str, str, object]]:
    """Yield provider factories declared by distributions in the source checkout."""

    source_roots = prepare_source_provider_imports()
    if not source_roots:
        return ()

    packages_root = source_roots[0].parents[1]
    result: list[tuple[str, str, object]] = []
    for metadata_path in sorted(packages_root.glob("*/pyproject.toml")):
        try:
            metadata = tomllib.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            continue

        entry_points = (
            metadata.get("project", {})
            .get("entry-points", {})
            .get(PROVIDER_ENTRY_POINT_GROUP, {})
        )
        if not isinstance(entry_points, dict) or not entry_points:
            continue

        for name, value in sorted(entry_points.items(), key=lambda item: str(item[0]).casefold()):
            module_name, separator, attribute = str(value).partition(":")
            if not separator or not module_name or not attribute:
                raise ValueError(f"invalid provider entry point {name!r}: {value!r}")
            module = importlib.import_module(module_name)
            factory = getattr(module, attribute)
            result.append((str(name), str(value), factory))

    return tuple(result)


def _instantiate(candidate: object) -> ConversationProvider:
    if isinstance(candidate, type):
        candidate = candidate()
    elif not isinstance(candidate, ConversationProvider) and callable(candidate):
        candidate = candidate()
    if not isinstance(candidate, ConversationProvider):
        raise TypeError("provider factory did not produce a ConversationProvider")
    return candidate


def discover_available_providers(
    *,
    include_embedded: bool = True,
    entry_points: Callable[[], object] | None = None,
    artifact_root: Path | str | None = None,
) -> ProviderDiscoveryResult:
    """Discover entry-point providers plus optional source-checkout packages.

    Isolated per-user managed provider roots are added before entry-point discovery so
    the same public packaging contract works in a normal Python checkout and in the
    Windows onedir executable. ``include_embedded=False`` means entry-point-only
    discovery and is used by the installation matrix.

    Installed/managed entry-point providers win when a source package exposes the same
    stable provider ID. Individual provider failures remain non-fatal.
    """

    prepare_managed_provider_imports(artifact_root)
    external = (
        discover_providers()
        if entry_points is None
        else discover_providers(entry_points=entry_points)
    )
    registry = external.registry
    failures = list(external.failures)
    successes = list(external.successes)
    registered = set(registry.provider_ids())

    if not include_embedded:
        return ProviderDiscoveryResult(
            registry=registry,
            failures=tuple(failures),
            successes=tuple(successes),
        )

    try:
        source_packages = _source_package_candidates()
    except Exception as error:
        failures.append(
            ProviderDiscoveryFailure(
                name="source-packages",
                value="packages/*/pyproject.toml",
                error=f"{type(error).__name__}: {error}",
            )
        )
        source_packages = ()

    for name, value, factory in source_packages:
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
            successes.append(
                ProviderDiscoverySuccess(
                    name=name,
                    value=value,
                    provider_id=str(descriptor.provider_id),
                )
            )
        except Exception as error:
            failures.append(
                ProviderDiscoveryFailure(
                    name=name,
                    value=value,
                    error=f"{type(error).__name__}: {error}",
                )
            )

    return ProviderDiscoveryResult(
        registry=registry,
        failures=tuple(failures),
        successes=tuple(successes),
    )


__all__ = [
    "discover_available_providers",
    "prepare_managed_provider_imports",
    "prepare_source_provider_imports",
]
