"""Workspace selection and persistence for exporter-core.

A provider describes how to collect and interpret one source. A workspace
selects one provider together with the archive root on which the application is
currently operating. Keeping these concepts separate allows multiple archives
to use the same provider later (for example personal and work ChatGPT archives).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from gpt_exporter.paths import ArchivePaths
from gpt_exporter.providers import BUILTIN_PROVIDERS, ExporterProvider, ProviderRegistry


WORKSPACE_CONFIG_VERSION = 1
DEFAULT_WORKSPACE_CONFIG = Path.home() / ".gpt_exporter_workspaces.json"


@dataclass(frozen=True, slots=True)
class Workspace:
    key: str
    display_name: str
    provider: ExporterProvider
    archive_root: Path

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("Workspace key must not be empty.")
        if not self.display_name.strip():
            raise ValueError("Workspace display name must not be empty.")
        object.__setattr__(self, "archive_root", Path(self.archive_root).expanduser().resolve())

    @property
    def paths(self) -> ArchivePaths:
        return ArchivePaths.from_root(self.archive_root)

    @property
    def database_path(self) -> Path:
        return self.paths.database


class WorkspaceRegistry:
    def __init__(self, workspaces: Iterable[Workspace] = ()) -> None:
        self._workspaces: dict[str, Workspace] = {}
        for workspace in workspaces:
            self.register(workspace)

    def register(self, workspace: Workspace) -> None:
        normalized = workspace.key.strip().casefold()
        if not normalized:
            raise ValueError("Workspace key must not be empty.")
        if normalized in self._workspaces:
            raise ValueError(f"Duplicate workspace key: {workspace.key}")
        self._workspaces[normalized] = workspace

    def replace(self, workspace: Workspace) -> None:
        normalized = workspace.key.strip().casefold()
        if not normalized:
            raise ValueError("Workspace key must not be empty.")
        if normalized not in self._workspaces:
            raise KeyError(f"Unknown workspace: {workspace.key}")
        self._workspaces[normalized] = workspace

    def remove(self, key: str) -> Workspace:
        normalized = key.strip().casefold()
        try:
            return self._workspaces.pop(normalized)
        except KeyError as error:
            raise KeyError(f"Unknown workspace: {key}") from error

    def get(self, key: str) -> Workspace:
        normalized = key.strip().casefold()
        try:
            return self._workspaces[normalized]
        except KeyError as error:
            raise KeyError(f"Unknown workspace: {key}") from error

    def all(self) -> tuple[Workspace, ...]:
        return tuple(sorted(self._workspaces.values(), key=lambda item: item.display_name.casefold()))

    def __len__(self) -> int:
        return len(self._workspaces)


def default_documents_root() -> Path:
    return Path(os.environ.get("USERPROFILE") or Path.home()).expanduser().resolve() / "Documents"


def build_default_workspaces(
    providers: ProviderRegistry = BUILTIN_PROVIDERS,
    *,
    documents_root: Path | str | None = None,
) -> WorkspaceRegistry:
    documents = (
        Path(documents_root).expanduser().resolve()
        if documents_root is not None
        else default_documents_root()
    )
    return WorkspaceRegistry(
        Workspace(
            key=provider.key,
            display_name=provider.display_name,
            provider=provider,
            archive_root=documents / provider.archive_directory_name,
        )
        for provider in providers.all()
    )


def save_workspace_registry(
    registry: WorkspaceRegistry,
    path: Path | str = DEFAULT_WORKSPACE_CONFIG,
) -> Path:
    """Persist workspace identity/provider/root without serializing provider code."""

    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": WORKSPACE_CONFIG_VERSION,
        "workspaces": [
            {
                "key": workspace.key,
                "display_name": workspace.display_name,
                "provider_key": workspace.provider.key,
                "archive_root": str(workspace.archive_root),
            }
            for workspace in registry.all()
        ],
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return target


def load_workspace_registry(
    path: Path | str = DEFAULT_WORKSPACE_CONFIG,
    *,
    providers: ProviderRegistry = BUILTIN_PROVIDERS,
    fallback_to_defaults: bool = True,
) -> WorkspaceRegistry:
    """Load configured workspaces; unknown providers are rejected explicitly."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        if fallback_to_defaults:
            return build_default_workspaces(providers)
        raise FileNotFoundError(source)

    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != WORKSPACE_CONFIG_VERSION:
        raise ValueError(f"Unsupported workspace configuration: {source}")
    entries = data.get("workspaces")
    if not isinstance(entries, list):
        raise ValueError(f"Workspace configuration has no valid workspaces list: {source}")

    workspaces: list[Workspace] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid workspace entry in {source}")
        provider_key = str(item.get("provider_key") or "")
        provider = providers.get(provider_key)
        workspaces.append(
            Workspace(
                key=str(item.get("key") or ""),
                display_name=str(item.get("display_name") or ""),
                provider=provider,
                archive_root=Path(str(item.get("archive_root") or "")),
            )
        )

    registry = WorkspaceRegistry(workspaces)
    if not len(registry) and fallback_to_defaults:
        return build_default_workspaces(providers)
    return registry


BUILTIN_WORKSPACES = build_default_workspaces()
DEFAULT_WORKSPACE = BUILTIN_WORKSPACES.get("chatgpt")


__all__ = [
    "BUILTIN_WORKSPACES",
    "DEFAULT_WORKSPACE",
    "DEFAULT_WORKSPACE_CONFIG",
    "WORKSPACE_CONFIG_VERSION",
    "Workspace",
    "WorkspaceRegistry",
    "build_default_workspaces",
    "default_documents_root",
    "load_workspace_registry",
    "save_workspace_registry",
]
