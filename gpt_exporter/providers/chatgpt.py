"""ChatGPT source provider.

All ChatGPT-specific collection identity lives here. The existing importer is
kept unchanged behind the provider boundary while the rest of the application
is progressively made provider-neutral.
"""

from __future__ import annotations

from gpt_exporter.archive.importer import import_bundle
from gpt_exporter.resources import collector_path

from .base import ExporterProvider


CHATGPT_PROVIDER = ExporterProvider(
    key="chatgpt",
    display_name="ChatGPT",
    archive_directory_name="ChatGPT Archive",
    website_url="https://chatgpt.com/",
    source_bundle_name="chatgpt-archive-source.json",
    collector_path=collector_path(),
    importer=import_bundle,
)


__all__ = ["CHATGPT_PROVIDER"]
