"""In-process browser bundle import API for GPT Exporter.

The v2.9 package boundary calls the historical importer implementation directly
rather than launching ``import_browser_bundle.py`` in another Python process.
The compatibility module is imported with its filename diagnostic suppressed;
standalone CLI behavior remains unchanged when that script is executed itself.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Callable


ProgressCallback = Callable[[str], None]


class _ProgressStream(io.TextIOBase):
    """Translate writes from the compatibility importer into progress lines."""

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


_import_capture = io.StringIO()
with contextlib.redirect_stdout(_import_capture):
    import import_browser_bundle as _legacy_importer


ImportBundleResult = _legacy_importer.ImportBundleResult


def import_bundle(
    bundle_path: Path | str,
    *,
    archive_root: Path | str,
    progress: ProgressCallback | None = None,
) -> ImportBundleResult:
    """Import one browser-generated bundle into an explicit archive root.

    The implementation is synchronous and performs no console output unless a
    progress callback is supplied.  It does not mutate ``sys.argv`` and does not
    start another Python process.
    """

    stream = _ProgressStream(progress)
    try:
        with contextlib.redirect_stdout(stream):
            return _legacy_importer.import_bundle(
                bundle_path,
                archive_root=archive_root,
            )
    finally:
        stream.flush()


__all__ = ["ImportBundleResult", "import_bundle"]
