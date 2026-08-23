"""Packaged non-Python resources for GPT Exporter."""

from __future__ import annotations

from pathlib import Path


COLLECTOR_NAME = "collect_chatgpt_archive.js"


def collector_path() -> Path:
    """Return the packaged collector JavaScript path."""

    return Path(__file__).resolve().parent / COLLECTOR_NAME


def read_collector_source() -> str:
    """Read the packaged collector JavaScript and reject an empty resource."""

    path = collector_path()
    source = path.read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"Collector JavaScript is empty: {path}")
    return source


__all__ = ["COLLECTOR_NAME", "collector_path", "read_collector_source"]
