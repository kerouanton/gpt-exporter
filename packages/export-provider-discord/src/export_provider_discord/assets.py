"""Provider-owned acquisition of Discord media referenced by collector exports."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from gpt_exporter.assets import ASSET_BUCKETS, asset_bucket, asset_bucket_path, move_verified
from gpt_exporter.core import CanonicalAsset, CanonicalConversation


FetchBytes = Callable[[str], bytes]
_INVALID_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")
_IMAGE_SUFFIXES = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


@dataclass(frozen=True, slots=True)
class DiscordAssetDownloadResult:
    asset_directory: Path
    source_paths: dict[str, Path]
    downloaded: int
    reused: int
    failed: tuple[str, ...]

    @property
    def available(self) -> int:
        return len(self.source_paths)


def _safe_name(asset: CanonicalAsset) -> str:
    parsed = urlparse(asset.source_ref or "")
    source_name = unquote(Path(parsed.path).name)
    name = (asset.name or source_name or "asset").strip()
    name = _INVALID_FILENAME.sub("_", name).strip(" .") or "asset"
    digest = hashlib.sha256((asset.source_ref or asset.asset_id).encode("utf-8")).hexdigest()[:12]
    return f"{digest}_{name}"[:220]


def _http_fetch(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) 9c-conversation-archive/1",
            "Referer": "https://discord.com/",
            "Accept": "*/*",
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def _channel_id(conversation: CanonicalConversation) -> str:
    prefix = "discord:"
    value = conversation.conversation_id
    return value[len(prefix):] if value.startswith(prefix) else value


def _resolve_asset_roots(
    conversation: CanonicalConversation,
    asset_directory: Path | str,
) -> tuple[Path, Path | None]:
    """Accept both the historical assets/<channel> path and the canonical root."""
    requested = Path(asset_directory).expanduser().resolve()
    channel_id = _channel_id(conversation)
    if requested.name == channel_id and requested.parent.name.casefold() == "assets":
        return requested.parent, requested
    return requested, None


def _asset_suffix(asset: CanonicalAsset) -> str:
    name = str(asset.name or "").strip()
    if name:
        suffix = Path(name).suffix.casefold()
        if suffix:
            return suffix
    source = str(asset.source_ref or "").strip()
    return Path(urlparse(source).path).suffix.casefold() if source else ""


def _discord_asset_bucket(asset: CanonicalAsset) -> str:
    """Map Discord semantics onto the shared physical bucket taxonomy."""
    kind = str(asset.metadata.get("kind") or "").casefold()
    shared = asset_bucket(kind, asset.media_type)
    if shared == "external":
        return shared
    if kind == "sticker":
        return "image"
    if asset.media_type and asset.media_type.casefold().startswith("image/"):
        return "image"
    if kind in {"attachment", "linked-media"} and _asset_suffix(asset) in _IMAGE_SUFFIXES:
        return "image"
    return shared


def _archive_path(path: Path) -> str | None:
    for parent in (path.parent, *path.parents):
        if parent.name.casefold() == "assets":
            try:
                relative = path.relative_to(parent)
            except ValueError:
                return None
            return f"assets/{relative.as_posix()}"
    return None


def download_conversation_assets(
    conversation: CanonicalConversation,
    asset_directory: Path | str,
    *,
    fetch_bytes: FetchBytes | None = None,
) -> DiscordAssetDownloadResult:
    """Download Discord assets into the shared canonical bucket layout.

    The historical ``assets/<channel_id>`` input is still accepted. Existing
    files there are migrated lazily and verified before deletion.

    Failures are non-fatal: the canonical conversation keeps the original URL and
    the derived document falls back to that remote link.
    """

    assets_root, legacy_directory = _resolve_asset_roots(conversation, asset_directory)
    assets_root.mkdir(parents=True, exist_ok=True)
    for bucket in ASSET_BUCKETS:
        asset_bucket_path(assets_root, bucket).mkdir(parents=True, exist_ok=True)

    fetch = fetch_bytes or _http_fetch
    source_paths: dict[str, Path] = {}
    downloaded = 0
    reused = 0
    failed: list[str] = []

    for message in conversation.messages:
        for asset in message.assets:
            source = (asset.source_ref or "").strip()
            if not source or source in source_paths:
                continue
            parsed = urlparse(source)
            if parsed.scheme not in {"http", "https"}:
                continue

            filename = _safe_name(asset)
            bucket = _discord_asset_bucket(asset)
            target = asset_bucket_path(assets_root, bucket) / filename
            legacy = legacy_directory / filename if legacy_directory is not None else None

            if target.is_file() and target.stat().st_size > 0:
                source_paths[source] = target
                reused += 1
                continue

            if legacy is not None and legacy.is_file() and legacy.stat().st_size > 0:
                try:
                    move_verified(legacy, target)
                    source_paths[source] = target
                    reused += 1
                    continue
                except Exception as error:
                    failed.append(
                        f"{asset.name or asset.asset_id}: legacy migration: "
                        f"{type(error).__name__}: {error}"
                    )
                    continue

            temporary = target.with_name(target.name + ".part")
            try:
                payload = fetch(source)
                if not payload:
                    raise ValueError("empty response")
                temporary.write_bytes(payload)
                os.replace(temporary, target)
                source_paths[source] = target
                downloaded += 1
            except Exception as error:  # provider archive records the concrete URL/error
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                failed.append(f"{asset.name or asset.asset_id}: {type(error).__name__}: {error}")

    if legacy_directory is not None and legacy_directory.is_dir():
        try:
            legacy_directory.rmdir()
        except OSError:
            pass

    return DiscordAssetDownloadResult(
        asset_directory=assets_root,
        source_paths=source_paths,
        downloaded=downloaded,
        reused=reused,
        failed=tuple(failed),
    )


def conversation_with_local_assets(
    conversation: CanonicalConversation,
    source_paths: dict[str, Path],
    *,
    relative_to: Path | str,
) -> CanonicalConversation:
    """Return an export-only conversation whose available assets point locally.

    Historical deletion state remains metadata in the canonical archive.  The
    derived document receives only a quiet presentation annotation so archived
    text itself is never mutated on disk.
    """

    base = Path(relative_to).expanduser().resolve()
    messages = []
    for message in conversation.messages:
        assets = []
        for asset in message.assets:
            source = (asset.source_ref or "").strip()
            local = source_paths.get(source)
            if local is None:
                assets.append(asset)
                continue
            local_ref = os.path.relpath(local, start=base).replace(os.sep, "/")
            metadata = dict(asset.metadata)
            metadata["original_source_ref"] = source
            metadata["local_archive_asset"] = True
            archive_path = _archive_path(local)
            if archive_path:
                metadata["archive_path"] = archive_path
            assets.append(replace(asset, source_ref=local_ref, metadata=metadata))

        content = message.content
        if message.metadata.get("deleted"):
            content = f"*(deleted)*  {content}" if content else "*(deleted)*"
        messages.append(replace(message, content=content, assets=tuple(assets)))
    return replace(conversation, messages=tuple(messages))


__all__ = [
    "DiscordAssetDownloadResult",
    "conversation_with_local_assets",
    "download_conversation_assets",
]
