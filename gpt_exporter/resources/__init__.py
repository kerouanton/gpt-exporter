"""Packaged provider-neutral application resources."""

from __future__ import annotations

from pathlib import Path


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


def read_user_guide() -> str:
    """Read the packaged user guide Markdown."""

    return read_text_resource(HELP_NAME)


def read_release_history() -> str:
    """Read the packaged release-history Markdown."""

    return read_text_resource(HISTORY_NAME)


__all__ = [
    "HELP_NAME",
    "HISTORY_NAME",
    "read_release_history",
    "read_text_resource",
    "read_user_guide",
    "resource_path",
]
