"""Compatibility facade for the shared conversation browser core."""

import sys
from gpt_exporter.ui.browser import archive_core as _implementation

sys.modules[__name__] = _implementation
