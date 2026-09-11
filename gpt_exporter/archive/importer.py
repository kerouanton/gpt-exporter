"""Lazy compatibility facade for the ChatGPT browser-bundle importer."""


def _implementation():
    from gpt_exporter.provider_loader import prepare_source_provider_imports

    prepare_source_provider_imports()
    from export_provider_chatgpt import importer as implementation

    return implementation


def import_bundle(*args, **kwargs):
    return _implementation().import_bundle(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = ["ImportBundleResult", "import_bundle"]
