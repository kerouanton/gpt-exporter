"""Compatibility facade for the ChatGPT provider archive browser."""

import sys
from gpt_exporter.providers.gpt.ui.browser import archive_browser as _implementation

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
