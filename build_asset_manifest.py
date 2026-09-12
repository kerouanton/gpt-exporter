"""Compatibility launcher for the ChatGPT provider asset-manifest CLI."""

import sys
from pathlib import Path
from export_provider_chatgpt.cli import build_asset_manifest as _implementation

_implementation.ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
