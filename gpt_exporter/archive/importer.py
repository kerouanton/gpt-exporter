"""Lazy compatibility facade for the ChatGPT browser-bundle importer."""


def import_bundle(*args, **kwargs):
    from gpt_exporter.providers.gpt.importer import import_bundle as implementation
    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "ImportBundleResult":
        from gpt_exporter.providers.gpt.importer import ImportBundleResult
        return ImportBundleResult
    raise AttributeError(name)


__all__ = ["ImportBundleResult", "import_bundle"]
