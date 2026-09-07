"""Compatibility facade for the ChatGPT browser-bundle importer.

Provider-specific implementation lives in gpt_exporter.providers.gpt.importer.
New code must import the provider module directly.
"""

from gpt_exporter.providers.gpt.importer import ImportBundleResult, import_bundle

__all__ = ["ImportBundleResult", "import_bundle"]
