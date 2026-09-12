"""Temporary compatibility namespace used only while final legacy imports are audited."""

from __future__ import annotations

import importlib
import sys

_ALIASES = {
    "gpt": "export_provider_chatgpt",
    "discord": "export_provider_discord",
}

for _legacy_name, _package_name in _ALIASES.items():
    _qualified_name = f"{__name__}.{_legacy_name}"
    if _qualified_name not in sys.modules:
        try:
            sys.modules[_qualified_name] = importlib.import_module(_package_name)
        except ModuleNotFoundError as exc:
            if exc.name != _package_name:
                raise

del importlib, sys, _legacy_name, _package_name, _qualified_name
