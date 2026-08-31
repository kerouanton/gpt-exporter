"""Reusable archive-index APIs for exporter core and providers."""

from .engine import (
    IndexFailure,
    IndexUpdateResult,
    rebuild_index,
    update_index,
)
from .normalized import (
    ensure_provider_schema,
    index_normalized_conversation,
    index_normalized_file,
    initialize_normalized_database,
)
from .normalized_engine import update_normalized_index

__all__ = [
    "IndexFailure",
    "IndexUpdateResult",
    "ensure_provider_schema",
    "index_normalized_conversation",
    "index_normalized_file",
    "initialize_normalized_database",
    "rebuild_index",
    "update_index",
    "update_normalized_index",
]
