"""Compatibility namespace for historical concrete-provider imports.

Concrete providers now live in independent distributions.  The host must not
contain duplicate provider source trees, but old root-level launchers and
third-party imports may still refer to ``gpt_exporter.providers.gpt`` or
``gpt_exporter.providers.discord`` during the transition.

Importing this compatibility package installs aliases that point at the
extracted provider packages.  No provider implementation is stored here.
"""

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
