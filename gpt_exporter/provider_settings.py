"""Durable provider lifecycle preferences for MSNE.

Provider enable/disable state is kept outside provider packages so a disabled or
broken provider never needs to be imported merely to discover its preference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


SETTINGS_VERSION = 1


def default_provider_settings_path() -> Path:
    """Return the per-user provider settings path."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata)
    elif os.name == "nt":
        base = Path.home() / "AppData" / "Local"
    else:
        base = Path.home() / ".local" / "share"
    # Keep the established application-data directory during the controlled rename.
    return base / "GPT Exporter" / "providers.json"


class ProviderSettings:
    """Read/write the small durable set of provider IDs disabled by the user."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or default_provider_settings_path()).expanduser()

    def disabled_ids(self) -> frozenset[str]:
        if not self.path.is_file():
            return frozenset()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Unable to read provider settings: {self.path}") from error
        if not isinstance(payload, dict):
            raise ValueError("Provider settings must contain a JSON object")
        raw = payload.get("disabled", [])
        if not isinstance(raw, list):
            raise ValueError("Provider settings 'disabled' must be a JSON array")
        return frozenset(
            item.strip()
            for item in (str(value) for value in raw)
            if item.strip()
        )

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        provider_id = provider_id.strip()
        if not provider_id:
            raise ValueError("provider_id must not be empty")
        disabled = set(self.disabled_ids())
        if enabled:
            disabled.discard(provider_id)
        else:
            disabled.add(provider_id)
        payload = {
            "version": SETTINGS_VERSION,
            "disabled": sorted(disabled, key=str.casefold),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


__all__ = ["ProviderSettings", "default_provider_settings_path"]
