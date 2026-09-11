"""Lazy compatibility facade for the ChatGPT provider archive pipeline.

Provider-specific implementation lives in the extracted ChatGPT distribution.
New code should use provider capabilities directly. Importing this compatibility
module does not load or select a concrete provider.
"""


def _implementation():
    from gpt_exporter.provider_loader import prepare_source_provider_imports

    prepare_source_provider_imports()
    from export_provider_chatgpt import pipeline as implementation

    return implementation


def archive_bundle(*args, **kwargs):
    return _implementation().archive_bundle(*args, **kwargs)


def clear_generated_data(*args, **kwargs):
    return _implementation().clear_generated_data(*args, **kwargs)


def migrate_legacy_data(*args, **kwargs):
    return _implementation().migrate_legacy_data(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = ["archive_bundle", "clear_generated_data", "migrate_legacy_data"]
