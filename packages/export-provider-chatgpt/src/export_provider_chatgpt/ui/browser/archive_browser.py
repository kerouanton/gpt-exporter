"""Compatibility facade for the shared conversation browser implementation."""

import sys
from gpt_exporter.ui.browser import archive_browser as _implementation

sys.modules[__name__] = _implementation
