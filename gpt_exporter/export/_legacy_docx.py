"""Compatibility alias for the historical Markdown-to-DOCX v2.8 renderer."""

import sys
from . import _markdown_docx_v28 as _implementation

sys.modules[__name__] = _implementation
