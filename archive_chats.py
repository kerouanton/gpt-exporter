"""Compatibility launcher for the ChatGPT provider archive CLI."""

import sys
from pathlib import Path
from gpt_exporter.providers.gpt.cli import archive_chats as _implementation

# Preserve historical repository-root path semantics for callers importing this module.
_implementation.ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
