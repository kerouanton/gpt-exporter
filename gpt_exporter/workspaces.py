"""Provider-neutral named workspaces for the conversation application shell."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CATALOG_VERSION = 1


def default_workspace_catalog_path() -> Path:
    """Return the per-user workspace catalog path without importing providers."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    return base / "GPT Exporter" / "workspaces.json"


@dataclass(frozen=True, slots=True)
class ConversationWorkspace:
    """One named provider/archive-root pairing selected by the application shell."""

    name: str
    provider_id: str
    root_path: Path
    enabled: bool = True
    description: str = ""

    @property
    def database_path(self) -> Path:
        return self.root_path / "conversations-index.sqlite"

    def normalized(self) -> "ConversationWorkspace":
        name = self.name.strip()
        provider_id = self.provider_id.strip()
        if not name:
            raise ValueError("Workspace name cannot be empty")
        if not provider_id:
            raise ValueError("Workspace provider_id cannot be empty")
        return ConversationWorkspace(
            name=name,
            provider_id=provider_id,
            root_path=Path(self.root_path).expanduser(),
            enabled=bool(self.enabled),
            description=self.description.strip(),
        )


class WorkspaceCatalog:
    """Small durable workspace catalog owned by the application composition layer."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or default_workspace_catalog_path()).expanduser()

    def _read_payload(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"version": CATALOG_VERSION, "active_workspace": None, "workspaces": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to read workspace catalog: {self.path}") from error
        if not isinstance(payload, dict):
            raise ValueError("Workspace catalog must contain a JSON object")
        return payload

    def _write_payload(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _from_dict(raw: object) -> ConversationWorkspace:
        if not isinstance(raw, dict):
            raise ValueError("Workspace entry must be a JSON object")
        return ConversationWorkspace(
            name=str(raw.get("name") or ""),
            provider_id=str(raw.get("provider_id") or ""),
            root_path=Path(str(raw.get("root_path") or "")),
            enabled=bool(raw.get("enabled", True)),
            description=str(raw.get("description") or ""),
        ).normalized()

    @staticmethod
    def _to_dict(workspace: ConversationWorkspace) -> dict[str, object]:
        workspace = workspace.normalized()
        return {
            "name": workspace.name,
            "provider_id": workspace.provider_id,
            "root_path": str(workspace.root_path),
            "enabled": workspace.enabled,
            "description": workspace.description,
        }

    def list(self, *, enabled_only: bool = False) -> tuple[ConversationWorkspace, ...]:
        payload = self._read_payload()
        raw_items = payload.get("workspaces", [])
        if not isinstance(raw_items, list):
            raise ValueError("Workspace catalog 'workspaces' must be a JSON array")
        workspaces = tuple(self._from_dict(item) for item in raw_items)
        if enabled_only:
            workspaces = tuple(item for item in workspaces if item.enabled)
        return tuple(sorted(workspaces, key=lambda item: item.name.casefold()))

    def get(self, name: str) -> ConversationWorkspace:
        wanted = name.casefold().strip()
        for workspace in self.list():
            if workspace.name.casefold() == wanted:
                return workspace
        raise KeyError(f"Unknown workspace '{name}'")

    def seed(self, workspaces: Iterable[ConversationWorkspace]) -> None:
        payload = self._read_payload()
        existing = {item.name.casefold(): item for item in self.list()}
        changed = False
        for raw in workspaces:
            workspace = raw.normalized()
            if workspace.name.casefold() not in existing:
                existing[workspace.name.casefold()] = workspace
                changed = True
        if not changed and self.path.is_file():
            return
        payload["version"] = CATALOG_VERSION
        payload["workspaces"] = [
            self._to_dict(item)
            for item in sorted(existing.values(), key=lambda item: item.name.casefold())
        ]
        self._write_payload(payload)

    def get_active_name(self) -> str | None:
        value = self._read_payload().get("active_workspace")
        return str(value) if value else None

    def get_active(self) -> ConversationWorkspace | None:
        name = self.get_active_name()
        if not name:
            return None
        try:
            workspace = self.get(name)
        except KeyError:
            return None
        return workspace if workspace.enabled else None

    def set_active(self, name: str) -> ConversationWorkspace:
        workspace = self.get(name)
        if not workspace.enabled:
            raise ValueError(f"Workspace '{name}' is disabled")
        payload = self._read_payload()
        payload["version"] = CATALOG_VERSION
        payload["active_workspace"] = workspace.name
        if "workspaces" not in payload:
            payload["workspaces"] = [self._to_dict(item) for item in self.list()]
        self._write_payload(payload)
        return workspace


__all__ = [
    "CATALOG_VERSION",
    "ConversationWorkspace",
    "WorkspaceCatalog",
    "default_workspace_catalog_path",
]
