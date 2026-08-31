"""Workspace selection for exporter-core.

A provider describes how to collect and interpret one source. A workspace
selects one provider together with the archive root on which the application is
currently operating. Keeping these concepts separate allows multiple archives
to use the same provider later (for example personal and work ChatGPT archives).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from gpt_exporter.paths import ArchivePaths
from gpt_exporter.providers import BUILTIN_PROVIDERS, ExporterProvider, ProviderRegistry


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


BUILTIN_WORKSPACES = build_default_workspaces()
DEFAULT_WORKSPACE = BUILTIN_WORKSPACES.get("chatgpt")


__all__ = [
    "BUILTIN_WORKSPACES",
    "DEFAULT_WORKSPACE",
    "Workspace",
    "WorkspaceRegistry",
    "build_default_workspaces",
    "default_documents_root",
]
