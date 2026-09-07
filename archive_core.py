"""Compatibility facade for the ChatGPT provider archive browser core."""

import sys
from gpt_exporter.providers.gpt.ui.browser import archive_core as _implementation

sys.modules[__name__] = _implementation
