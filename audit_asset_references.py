"""Compatibility launcher for the ChatGPT provider asset-audit CLI."""

import sys
from gpt_exporter.providers.gpt.cli import audit_asset_references as _implementation

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
