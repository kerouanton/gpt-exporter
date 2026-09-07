"""ChatGPT browser-bundle import API."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Callable

from . import _bundle_importer

ProgressCallback = Callable[[str], None]
ImportBundleResult = _bundle_importer.ImportBundleResult


class _ProgressStream(io.TextIOBase):
    def __init__(self, progress: ProgressCallback | None) -> None:
        super().__init__()
        self.progress = progress
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if self.progress is not None:
                self.progress(line)
        return len(value)

    def flush(self) -> None:
        if self._buffer and self.progress is not None:
            self.progress(self._buffer)
        self._buffer = ""


def import_bundle(
    bundle_path: Path | str,
    *,
    archive_root: Path | str,
    progress: ProgressCallback | None = None,
) -> ImportBundleResult:
    """Import one ChatGPT browser collector bundle into an archive root."""
    stream = _ProgressStream(progress)
    try:
        with contextlib.redirect_stdout(stream):
            return _bundle_importer.import_bundle(
                bundle_path,
                archive_root=archive_root,
            )
    finally:
        stream.flush()


__all__ = ["ImportBundleResult", "import_bundle"]
