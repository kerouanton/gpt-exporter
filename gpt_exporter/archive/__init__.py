"""Archive compatibility APIs.

Concrete ChatGPT archive analysis and import implementations live under
``gpt_exporter.providers.gpt``. This package keeps historical entry points lazy
so importing it does not select or load a concrete provider.
"""


def import_bundle(*args, **kwargs):
    from .importer import import_bundle as implementation
    return implementation(*args, **kwargs)


def collect_media_inventory(*args, **kwargs):
    from .inventory import collect_media_inventory as implementation
    return implementation(*args, **kwargs)


def inventory_media(*args, **kwargs):
    from .inventory import inventory_media as implementation
    return implementation(*args, **kwargs)


def render_console_summary(*args, **kwargs):
    from .inventory import render_console_summary as implementation
    return implementation(*args, **kwargs)


def render_text_report(*args, **kwargs):
    from .inventory import render_text_report as implementation
    return implementation(*args, **kwargs)


def write_inventory_reports(*args, **kwargs):
    from .inventory import write_inventory_reports as implementation
    return implementation(*args, **kwargs)


def __getattr__(name: str):
    if name == "ImportBundleResult":
        from .importer import ImportBundleResult
        return ImportBundleResult
    if name == "InventoryResult":
        from .inventory import InventoryResult
        return InventoryResult
    raise AttributeError(name)


__all__ = [
    "ImportBundleResult",
    "InventoryResult",
    "collect_media_inventory",
    "import_bundle",
    "inventory_media",
    "render_console_summary",
    "render_text_report",
    "write_inventory_reports",
]
