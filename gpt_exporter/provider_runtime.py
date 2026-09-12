"""Runtime validation and dependency policy for managed provider wheels."""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
import re
import shutil
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from email.parser import Parser
from pathlib import Path

from gpt_exporter.core import ConversationProvider
from gpt_exporter.core.provider_discovery import (
    PROVIDER_API_VERSION,
    PROVIDER_ENTRY_POINT_GROUP,
    discover_providers,
)
from gpt_exporter.provider_artifacts import (
    ProviderArtifactInfo,
    ProviderArtifactStore,
    canonical_distribution_name,
)
from gpt_exporter.provider_loader import prepare_managed_provider_imports

_HOST_DISTRIBUTION = "gpt-exporter"
_REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def provider_wheel_dependencies(path: Path | str) -> tuple[str, ...]:
    """Return the wheel's declared runtime requirements verbatim."""
    wheel_path = Path(path).expanduser().resolve()
    with zipfile.ZipFile(wheel_path) as archive:
        metadata_names = [
            item.filename
            for item in archive.infolist()
            if item.filename.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise ValueError("Provider wheel must contain exactly one .dist-info/METADATA file")
        try:
            metadata = Parser().parsestr(
                archive.read(metadata_names[0]).decode("utf-8")
            )
        except UnicodeDecodeError as error:
            raise ValueError("Provider wheel METADATA is not UTF-8") from error
    return tuple(value.strip() for value in metadata.get_all("Requires-Dist", []) if value.strip())


def validate_provider_dependency_policy(path: Path | str) -> tuple[str, ...]:
    """Reject dependencies MSNE's isolated installer cannot safely resolve yet.

    Stage C intentionally supports self-contained provider wheels. The only permitted
    external runtime requirement is the MSNE host distribution itself. Third-party
    provider dependencies will be handled explicitly by a later dependency/bundle
    contract instead of silently leaking into the global Python environment.
    """
    requirements = provider_wheel_dependencies(path)
    unsupported: list[str] = []
    for requirement in requirements:
        match = _REQUIREMENT_NAME_RE.match(requirement)
        if match is None:
            unsupported.append(requirement)
            continue
        name = canonical_distribution_name(match.group(1))
        if name != _HOST_DISTRIBUTION:
            unsupported.append(requirement)
    if unsupported:
        joined = "\n  ".join(unsupported)
        raise ValueError(
            "Provider wheel declares unsupported runtime dependencies. "
            "Managed provider wheels must currently be self-contained except for "
            f"{_HOST_DISTRIBUTION!r}:\n  {joined}"
        )
    return requirements


def _path_belongs_to_root(value: object, root: Path) -> bool:
    if not value:
        return False
    try:
        resolved = Path(str(value)).resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        return False
    return resolved == root or root in resolved.parents


def _module_belongs_to_root(module: object, root: Path) -> bool:
    if _path_belongs_to_root(getattr(module, "__file__", None), root):
        return True
    package_paths = getattr(module, "__path__", ()) or ()
    return any(_path_belongs_to_root(item, root) for item in package_paths)


@contextmanager
def _fresh_provider_modules(root: Path, module_names: tuple[str, ...]):
    """Temporarily load all provider-owned modules from ``root`` in a clean scope."""
    root = root.resolve()
    top_level = {name.split(".", 1)[0] for name in module_names if name}
    saved = {
        name: module
        for name, module in tuple(sys.modules.items())
        if name.split(".", 1)[0] in top_level or _module_belongs_to_root(module, root)
    }
    for name in saved:
        sys.modules.pop(name, None)

    root_text = str(root)
    sys.path.insert(0, root_text)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        if sys.path and sys.path[0] == root_text:
            sys.path.pop(0)
        else:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
        for name, module in tuple(sys.modules.items()):
            if name.split(".", 1)[0] in top_level or _module_belongs_to_root(module, root):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
        importlib.invalidate_caches()


def _other_provider_ids(
    store: ProviderArtifactStore,
    distribution_name: str,
) -> frozenset[str]:
    """Return provider IDs exposed by every other installed entry-point distribution."""
    prepare_managed_provider_imports(store.root)
    incoming_distribution = canonical_distribution_name(distribution_name)
    entries = []
    for entry in importlib_metadata.entry_points():
        if getattr(entry, "group", None) != PROVIDER_ENTRY_POINT_GROUP:
            continue
        distribution = getattr(entry, "dist", None)
        name = ""
        if distribution is not None:
            try:
                name = str(distribution.metadata.get("Name", "") or "")
            except Exception:
                name = ""
        if name and canonical_distribution_name(name) == incoming_distribution:
            continue
        entries.append(entry)
    discovery = discover_providers(entry_points=lambda: tuple(entries))
    return frozenset(discovery.registry.provider_ids())


def validate_managed_provider_runtime(
    root: Path | str,
    artifact: ProviderArtifactInfo,
    *,
    reserved_provider_ids: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Load and validate every provider entry point from one installed distribution."""
    provider_root = Path(root).expanduser().resolve()
    distributions = [
        item
        for item in importlib_metadata.distributions(path=[str(provider_root)])
        if canonical_distribution_name(item.metadata.get("Name", ""))
        == canonical_distribution_name(artifact.distribution_name)
    ]
    if len(distributions) != 1:
        raise ValueError(
            f"Expected exactly one installed distribution for {artifact.distribution_name!r}"
        )

    distribution = distributions[0]
    entries = tuple(
        item
        for item in distribution.entry_points
        if item.group == PROVIDER_ENTRY_POINT_GROUP
    )
    if not entries:
        raise ValueError("Installed provider exposes no provider entry points")

    expected = set(artifact.entry_points)
    actual = {(item.name, item.value) for item in entries}
    if actual != expected:
        raise ValueError("Installed provider entry points differ from the approved wheel")

    module_names = tuple(item.value.partition(":")[0].strip() for item in entries)
    provider_ids: list[str] = []
    with _fresh_provider_modules(provider_root, module_names):
        for entry in entries:
            candidate = entry.load()
            if isinstance(candidate, type):
                candidate = candidate()
            elif not isinstance(candidate, ConversationProvider) and callable(candidate):
                candidate = candidate()
            if not isinstance(candidate, ConversationProvider):
                raise TypeError(
                    f"Provider entry point {entry.name!r} did not produce a ConversationProvider"
                )
            descriptor = candidate.descriptor
            provider_id = str(descriptor.provider_id).strip()
            if not provider_id:
                raise ValueError(f"Provider entry point {entry.name!r} has an empty provider id")
            api_version = int(getattr(descriptor, "api_version", PROVIDER_API_VERSION))
            if api_version != PROVIDER_API_VERSION:
                raise ValueError(
                    f"Provider {provider_id!r} API version {api_version} is incompatible "
                    f"with core API version {PROVIDER_API_VERSION}"
                )
            if provider_id in provider_ids:
                raise ValueError(f"Duplicate provider id in distribution: {provider_id!r}")
            if provider_id in reserved_provider_ids:
                raise ValueError(
                    f"Provider id {provider_id!r} is already supplied by another distribution"
                )
            provider_ids.append(provider_id)
    return tuple(provider_ids)


def _restore_provider_snapshot(
    destination: Path,
    rollback: Path,
    *,
    had_previous: bool,
) -> None:
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    if had_previous and rollback.exists():
        rollback.replace(destination)
    importlib.invalidate_caches()


def install_provider_with_validation(
    store: ProviderArtifactStore,
    artifact: ProviderArtifactInfo,
) -> tuple[ProviderArtifactInfo, tuple[str, ...]]:
    """Install/update one provider and restore the previous managed copy on failure."""
    validate_provider_dependency_policy(artifact.path)
    reserved_provider_ids = _other_provider_ids(store, artifact.distribution_name)
    destination = store.destination_for(artifact)
    store.root.mkdir(parents=True, exist_ok=True)
    rollback_parent = Path(tempfile.mkdtemp(prefix=".runtime-rollback-", dir=store.root))
    rollback = rollback_parent / "previous"
    had_previous = destination.is_dir()
    if had_previous:
        shutil.copytree(destination, rollback)

    try:
        try:
            installed = store.install(artifact)
        except Exception as error:
            _restore_provider_snapshot(
                destination,
                rollback,
                had_previous=had_previous,
            )
            raise ValueError(
                "Provider installation failed; the previous managed version was restored"
                if had_previous
                else "Provider installation failed; no managed copy was kept"
            ) from error
        try:
            provider_ids = validate_managed_provider_runtime(
                destination,
                installed,
                reserved_provider_ids=reserved_provider_ids,
            )
        except Exception as error:
            _restore_provider_snapshot(
                destination,
                rollback,
                had_previous=had_previous,
            )
            raise ValueError(
                "Provider runtime validation failed; the previous managed version was restored"
                if had_previous
                else "Provider runtime validation failed; no managed copy was kept"
            ) from error
        return installed, provider_ids
    finally:
        shutil.rmtree(rollback_parent, ignore_errors=True)


__all__ = [
    "install_provider_with_validation",
    "provider_wheel_dependencies",
    "validate_managed_provider_runtime",
    "validate_provider_dependency_policy",
]
