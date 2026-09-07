"""Compatibility launcher for the ChatGPT provider GUI application."""

from __future__ import annotations

import sys

from gpt_exporter.providers.gpt.ui import app as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())

# Preserve the historical import surface for tests and external callers while
# keeping the concrete ChatGPT application implementation under its provider.
sys.modules[__name__] = _implementation
