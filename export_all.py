"""Compatibility launcher for the ChatGPT provider batch-export CLI."""

import sys
from gpt_exporter.providers.gpt.cli import export_all as _implementation

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
