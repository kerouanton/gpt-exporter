"""Byte-preserving storage helpers for Discord raw collector exports."""

from __future__ import annotations

import json
import lzma
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def is_xz_path(path: Path) -> bool:
    return Path(path).name.casefold().endswith(".xz")


def read_raw_bytes(path: Path) -> bytes:
    path = Path(path)
    if is_xz_path(path):
        with lzma.open(path, "rb") as handle:
            return handle.read()
    return path.read_bytes()


def read_raw_json(path: Path) -> object:
    return json.loads(read_raw_bytes(path).decode("utf-8-sig"))


def write_raw_archive(source_path: Path, destination_path: Path) -> Path:
    """Store raw collector bytes as XZ without reparsing or rewriting JSON."""
    source_path = Path(source_path).expanduser().resolve()
    destination_path = Path(destination_path).expanduser().resolve()
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    if is_xz_path(source_path):
        if destination_path.exists() and source_path.samefile(destination_path):
            return destination_path
        shutil.copyfile(source_path, destination_path)
        return destination_path

    with source_path.open("rb") as source, lzma.open(destination_path, "wb") as destination:
        shutil.copyfileobj(source, destination, length=1024 * 1024)
    return destination_path


def migrate_plain_raw_file(path: Path, destination: Path | None = None) -> Path:
    """Compress one historical raw JSON and remove it only after byte verification."""
    path = Path(path).expanduser().resolve()
    if destination is None:
        destination = path if is_xz_path(path) else path.with_name(path.name + ".xz")
    destination = Path(destination).expanduser().resolve()

    if is_xz_path(path):
        if path == destination or (destination.exists() and path.samefile(destination)):
            return destination
        original = read_raw_bytes(path)
        write_raw_archive(path, destination)
        if read_raw_bytes(destination) != original:
            destination.unlink(missing_ok=True)
            raise OSError(f"Raw XZ verification failed: {path}")
        path.unlink()
        return destination

    original = path.read_bytes()
    write_raw_archive(path, destination)
    if read_raw_bytes(destination) != original:
        destination.unlink(missing_ok=True)
        raise OSError(f"Raw XZ verification failed: {path}")
    path.unlink()
    return destination


def iter_raw_files(raw_dir: Path) -> tuple[Path, ...]:
    """Return compressed raw exports first, plus historical plain JSON files."""
    raw_dir = Path(raw_dir)
    compressed = sorted(raw_dir.glob("*.json.xz"))
    plain = sorted(raw_dir.glob("*.json"))
    return tuple(compressed + plain)


@contextmanager
def materialize_raw_json(path: Path) -> Iterator[Path]:
    """Yield a plain JSON path for code that predates compressed raw archives."""
    path = Path(path).expanduser().resolve()
    if not is_xz_path(path):
        yield path
        return

    with tempfile.TemporaryDirectory(prefix=".discord-raw-") as temporary:
        target_name = path.name[:-3] if path.name.casefold().endswith(".xz") else path.name
        target = Path(temporary) / target_name
        target.write_bytes(read_raw_bytes(path))
        yield target


__all__ = [
    "is_xz_path",
    "iter_raw_files",
    "materialize_raw_json",
    "migrate_plain_raw_file",
    "read_raw_bytes",
    "read_raw_json",
    "write_raw_archive",
]
