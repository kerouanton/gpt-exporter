"""Lazy compatibility facade for the ChatGPT batch export workflow.

The concrete JSON/XZ archive workflow lives in the extracted ChatGPT provider
package. Importing this module alone does not load a concrete provider.
"""


def _implementation():
    from gpt_exporter.provider_loader import prepare_source_provider_imports

    prepare_source_provider_imports()
    from export_provider_chatgpt.export import batch as implementation

    return implementation


def export_batch(*args, **kwargs):
    return _implementation().export_batch(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = ["BatchExportResult", "export_batch"]
