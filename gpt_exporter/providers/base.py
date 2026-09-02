"""Provider contract for source-specific exporter integrations.

The exporter core owns the archive layout, GUI, indexing/search experience,
organization metadata, derived exports, logging, and task orchestration.
Providers describe only source-specific collection, ingestion, and normalization
behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from gpt_exporter.model import Conversation


ProgressCallback = Callable[[str], None]


class BundleImporter(Protocol):
    """Import one provider-native source bundle into an archive root."""

    def __call__(
        self,
        bundle_path: Path | str,
        *,
        archive_root: Path | str,
        progress: ProgressCallback | None = None,
    ): ...


class ConversationNormalizer(Protocol):
    """Normalize one preserved provider-native conversation."""

    def __call__(
        self,
        input_path: Path | str,
        **kwargs,
    ) -> Conversation: ...


@dataclass(frozen=True, slots=True)
class ExporterProvider:
    """Source-specific integration metadata and hooks.

    This deliberately contains no Tk widgets, SQLite browser queries, project
    management, keyword-cloud logic, or DOCX rendering. Those responsibilities
    belong to the exporter core.
    """

    key: str
    display_name: str
    archive_directory_name: str
    website_url: str
    source_bundle_name: str
    collector_path: Path
    importer: BundleImporter
    normalizer: ConversationNormalizer

    @property
    def collector_name(self) -> str:
        return self.collector_path.name

    def read_collector_source(self) -> str:
        source = self.collector_path.read_text(encoding="utf-8")
        if not source.strip():
            raise ValueError(f"Collector JavaScript is empty: {self.collector_path}")
        return source

    def normalize_conversation(
        self,
        input_path: Path | str,
        **kwargs,
    ) -> Conversation:
        """Normalize one preserved native conversation through this provider."""
        return self.normalizer(input_path, **kwargs)


__all__ = [
    "BundleImporter",
    "ConversationNormalizer",
    "ExporterProvider",
    "ProgressCallback",
]
