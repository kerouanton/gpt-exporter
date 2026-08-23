"""Packaged non-Python resources for GPT Exporter."""

from __future__ import annotations

from pathlib import Path


COLLECTOR_NAME = "collect_chatgpt_archive.js"
HELP_NAME = "HELP.md"
HISTORY_NAME = "HISTORY.md"


def resource_path(name: str) -> Path:
    """Return the physical path of one packaged application resource."""

    return Path(__file__).resolve().parent / name


def read_text_resource(name: str) -> str:
    """Read a UTF-8 text resource and reject an empty resource."""

    path = resource_path(name)
    source = path.read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"Application resource is empty: {path}")
    return source


def collector_path() -> Path:
    """Return the packaged collector JavaScript path."""

    return resource_path(COLLECTOR_NAME)


def read_collector_source() -> str:
    """Read the packaged collector JavaScript and reject an empty resource."""

    return read_text_resource(COLLECTOR_NAME)


def read_user_guide() -> str:
    """Read the packaged user guide Markdown."""

    return read_text_resource(HELP_NAME)


def read_release_history() -> str:
    """Read the packaged release-history Markdown."""

    return read_text_resource(HISTORY_NAME)


__all__ = [
    "COLLECTOR_NAME",
    "HELP_NAME",
    "HISTORY_NAME",
    "collector_path",
    "read_collector_source",
    "read_release_history",
    "read_text_resource",
    "read_user_guide",
    "resource_path",
]
