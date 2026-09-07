"""Compatibility facade for the ChatGPT provider archive pipeline.

Provider-specific implementation lives in ``gpt_exporter.providers.gpt.pipeline``.
New code must import the provider module directly.  This facade deliberately
preserves the former public/module-level surface during the transition.
"""

from gpt_exporter.providers.gpt import pipeline as _implementation


for _name in dir(_implementation):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_implementation, _name)


__all__ = [name for name in globals() if not name.startswith("_")]
