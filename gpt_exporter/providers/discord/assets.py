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

from gpt_exporter.core import CanonicalAsset, CanonicalConversation


FetchBytes = Callable[[str], bytes]
_INVALID_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


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


def download_conversation_assets(
    conversation: CanonicalConversation,
    asset_directory: Path | str,
    *,
    fetch_bytes: FetchBytes | None = None,
) -> DiscordAssetDownloadResult:
    """Download unique HTTP(S) assets while their Discord URLs are still valid.

    Failures are non-fatal: the canonical conversation keeps the original URL and
    the derived document falls back to that remote link.
    """

    directory = Path(asset_directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
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
            target = directory / _safe_name(asset)
            if target.is_file() and target.stat().st_size > 0:
                source_paths[source] = target
                reused += 1
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

    return DiscordAssetDownloadResult(
        asset_directory=directory,
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
    """Return an export-only conversation whose available assets point locally."""

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
            assets.append(replace(asset, source_ref=local_ref, metadata=metadata))
        messages.append(replace(message, assets=tuple(assets)))
    return replace(conversation, messages=tuple(messages))


__all__ = [
    "DiscordAssetDownloadResult",
    "conversation_with_local_assets",
    "download_conversation_assets",
]
