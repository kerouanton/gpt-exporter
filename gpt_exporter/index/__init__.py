"""Archive-index APIs.

The engine is provider-neutral. Historical ``gpt_exporter.index.update_index``
remains a lazy ChatGPT compatibility entry point while callers migrate to the
provider adapter.
"""

from .engine import IndexFailure, IndexUpdateResult


def _implementation():
    from gpt_exporter.provider_loader import prepare_source_provider_imports

    prepare_source_provider_imports()
    from export_provider_chatgpt import indexing as implementation

    return implementation


def update_index(*args, **kwargs):
    return _implementation().update_index(*args, **kwargs)


def rebuild_index(*args, **kwargs):
    return _implementation().rebuild_index(*args, **kwargs)


__all__ = ["IndexFailure", "IndexUpdateResult", "rebuild_index", "update_index"]
