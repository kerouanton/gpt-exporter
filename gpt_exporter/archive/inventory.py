"""Lazy compatibility facade for ChatGPT media inventory analysis."""


def _implementation():
    from gpt_exporter.providers.gpt.archive import inventory as implementation
    return implementation


def collect_media_inventory(*args, **kwargs):
    return _implementation().collect_media_inventory(*args, **kwargs)


def inventory_media(*args, **kwargs):
    return _implementation().inventory_media(*args, **kwargs)


def render_console_summary(*args, **kwargs):
    return _implementation().render_console_summary(*args, **kwargs)


def render_text_report(*args, **kwargs):
    return _implementation().render_text_report(*args, **kwargs)


def write_inventory_reports(*args, **kwargs):
    return _implementation().write_inventory_reports(*args, **kwargs)


def __getattr__(name: str):
    return getattr(_implementation(), name)


__all__ = [
    "InventoryResult",
    "collect_media_inventory",
    "inventory_media",
    "render_console_summary",
    "render_text_report",
    "write_inventory_reports",
]
