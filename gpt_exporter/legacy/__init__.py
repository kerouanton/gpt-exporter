"""Legacy ChatGPT archive import helpers.

The legacy package is deliberately read-only at this stage.  It inventories
historical DOCX copies of ChatGPT conversations and produces structured reports
without mutating the canonical archive or SQLite index.
"""

from .docx import (
    LegacyDocxReport,
    LegacyFilenameMetadata,
    scan_legacy_docx,
    scan_legacy_directory,
)

__all__ = [
    "LegacyDocxReport",
    "LegacyFilenameMetadata",
    "scan_legacy_docx",
    "scan_legacy_directory",
]
