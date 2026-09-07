"""Archive-index APIs.

The engine is provider-neutral. Historical ``gpt_exporter.index.update_index``
remains a lazy ChatGPT compatibility entry point while callers migrate to the
provider adapter.
"""

from .engine import IndexFailure, IndexUpdateResult


def update_index(*args, **kwargs):
    from gpt_exporter.providers.gpt.indexing import update_index as provider_update_index
    return provider_update_index(*args, **kwargs)


def rebuild_index(*args, **kwargs):
    from gpt_exporter.providers.gpt.indexing import rebuild_index as provider_rebuild_index
    return provider_rebuild_index(*args, **kwargs)


__all__ = ["IndexFailure", "IndexUpdateResult", "rebuild_index", "update_index"]
