"""Lazy compatibility facade for the ChatGPT batch export workflow.

The concrete JSON/XZ archive workflow lives under
``gpt_exporter.providers.gpt.export.batch``. Importing this module alone does
not load a concrete provider.
"""


def export_batch(*args, **kwargs):
    from gpt_exporter.providers.gpt.export.batch import export_batch as implementation
    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "BatchExportResult":
        from gpt_exporter.providers.gpt.export.batch import BatchExportResult
        return BatchExportResult
    raise AttributeError(name)


__all__ = ["BatchExportResult", "export_batch"]
