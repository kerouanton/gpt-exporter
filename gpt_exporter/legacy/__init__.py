"""Legacy ChatGPT archive import helpers.

The legacy package is deliberately non-destructive. It inventories historical
DOCX copies and can build a versioned intermediate representation without
mutating the canonical archive or SQLite index.
"""

from .docx import (
    LegacyDocxReport,
    LegacyFilenameMetadata,
    scan_legacy_docx,
    scan_legacy_directory,
)
from .model import LEGACY_SCHEMA, LegacyBlock, LegacyConversation
from .parser import PARSER_VERSION, parse_legacy_conversation

__all__ = [
    "LEGACY_SCHEMA",
    "PARSER_VERSION",
    "LegacyBlock",
    "LegacyConversation",
    "LegacyDocxReport",
    "LegacyFilenameMetadata",
    "parse_legacy_conversation",
    "scan_legacy_docx",
    "scan_legacy_directory",
]
