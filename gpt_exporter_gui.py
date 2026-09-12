"""Compatibility launcher for the selectable conversation provider application."""

from __future__ import annotations

import sys


if __name__ == "__main__":
    from gpt_exporter.application import main as _main

    raise SystemExit(_main())

# Preserve the historical import surface for tests and external callers while
# keeping the concrete ChatGPT application implementation under its provider.
from export_provider_chatgpt.ui import app as _implementation

sys.modules[__name__] = _implementation
