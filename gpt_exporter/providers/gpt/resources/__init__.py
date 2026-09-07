"""Packaged resources for the ChatGPT provider."""

from pathlib import Path

COLLECTOR_NAME = "collect_chatgpt_archive.js"


def resource_path(name: str) -> Path:
    return Path(__file__).resolve().parent / name


def collector_path() -> Path:
    return resource_path(COLLECTOR_NAME)


def read_collector_source() -> str:
    path = collector_path()
    source = path.read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"ChatGPT collector resource is empty: {path}")
    return source


__all__ = ["COLLECTOR_NAME", "collector_path", "read_collector_source", "resource_path"]
