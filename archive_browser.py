"""Compatibility facade for the shared conversation archive browser."""

import sys
from gpt_exporter.ui.browser import archive_browser as _implementation

if __name__ == "__main__":
    _implementation.__file__ = __file__
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
