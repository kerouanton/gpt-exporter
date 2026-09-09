"""Provider-neutral archive asset taxonomy and safe file migration helpers."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path


ASSET_BUCKETS = ("attachment", "dictation", "image", "external")
_EXTERNAL_KINDS = {
    "external",
    "external-image",
    "external_image",
    "external-preview",
    "youtube-thumbnail",
    "author-avatar",
    "web-image",
}
_IMAGE_KINDS = {"image", "generated-image", "generated_image"}
_DICTATION_KINDS = {"dictation"}


def asset_bucket(kind: str | None, media_type: str | None = None) -> str:
    """Return the canonical physical bucket for one semantic asset kind."""
    normalized = str(kind or "").strip().casefold()
    if normalized in _EXTERNAL_KINDS or normalized.startswith("external-"):
        return "external"
    if normalized in _DICTATION_KINDS:
        return "dictation"
    if normalized in _IMAGE_KINDS:
        return "image"

    media = str(media_type or "").strip().casefold()
    if normalized == "" and media.startswith("image/"):
        return "image"
    return "attachment"


def asset_bucket_path(assets_root: Path | str, bucket: str) -> Path:
    """Return a validated canonical asset bucket path."""
    normalized = str(bucket).strip().casefold()
    if normalized not in ASSET_BUCKETS:
        raise ValueError(f"Unsupported asset bucket: {bucket!r}")
    return Path(assets_root) / normalized


def sha256_file(path: Path | str) -> str:
    """Hash one file without loading it entirely into memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def move_verified(source: Path | str, destination: Path | str) -> Path:
    """Move a file only after the destination is verified byte-identical.

    Existing identical destinations are reused. Conflicting destinations abort
    without deleting either file.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    if source_path.resolve() == destination_path.resolve():
        return destination_path
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source_digest = sha256_file(source_path)

    if destination_path.exists():
        if not destination_path.is_file() or sha256_file(destination_path) != source_digest:
            raise RuntimeError(
                "Asset migration conflict: destination exists with different contents: "
                f"{destination_path}"
            )
        source_path.unlink()
        return destination_path

    temporary = destination_path.with_name(destination_path.name + ".migrating")
    try:
        shutil.copy2(source_path, temporary)
        if sha256_file(temporary) != source_digest:
            raise RuntimeError(f"Asset migration verification failed: {source_path}")
        os.replace(temporary, destination_path)
        source_path.unlink()
    finally:
        temporary.unlink(missing_ok=True)

    return destination_path


__all__ = [
    "ASSET_BUCKETS",
    "asset_bucket",
    "asset_bucket_path",
    "move_verified",
    "sha256_file",
]
