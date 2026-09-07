"""Compatibility facade for the ChatGPT provider archive pipeline.

Provider-specific implementation lives in gpt_exporter.providers.gpt.pipeline.
New code must import the provider module directly.
"""

from gpt_exporter.providers.gpt.pipeline import *  # noqa: F401,F403
