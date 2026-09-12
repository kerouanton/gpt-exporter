"""Origin-pinned HTTPS transport and cache for provider catalog metadata."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from gpt_exporter.provider_artifacts import default_provider_directory
from gpt_exporter.provider_catalog import ProviderCatalog

_DEFAULT_MAX_BYTES = 1024 * 1024
_DEFAULT_TIMEOUT = 10.0


def default_catalog_cache_path() -> Path:
    """Return the durable per-user cache path for the validated catalog snapshot."""
    return default_provider_directory().parent / "catalog" / "provider-catalog.json"


def _normalized_host(value: str) -> str:
    return value.strip().rstrip(".").casefold()


def _validate_catalog_url(url: str, allowed_hosts: tuple[str, ...]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Provider catalog URL must use HTTPS")
    allowed = {_normalized_host(host) for host in allowed_hosts if host.strip()}
    if not allowed:
        raise ValueError("Provider catalog transport requires at least one pinned HTTPS host")
    if _normalized_host(parsed.hostname) not in allowed:
        raise ValueError(f"Provider catalog host is not trusted: {parsed.hostname!r}")


def fetch_provider_catalog(
    url: str,
    *,
    allowed_hosts: tuple[str, ...],
    timeout: float = _DEFAULT_TIMEOUT,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    opener: Callable[..., object] = urlopen,
) -> tuple[ProviderCatalog, str]:
    """Fetch and validate one catalog through a pinned HTTPS origin.

    Redirects are permitted only when the final URL still uses HTTPS and resolves to
    one of ``allowed_hosts``. The response size is bounded before JSON parsing.
    """
    if max_bytes <= 0:
        raise ValueError("Provider catalog maximum response size must be positive")
    _validate_catalog_url(url, allowed_hosts)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "MSNE-ProviderCatalog/1",
        },
    )
    response = opener(request, timeout=timeout)
    close = getattr(response, "close", None)
    try:
        final_url = str(getattr(response, "geturl")())
        _validate_catalog_url(final_url, allowed_hosts)
        read = getattr(response, "read")
        payload = read(max_bytes + 1)
    finally:
        if callable(close):
            close()
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError("Provider catalog response was not bytes")
    if len(payload) > max_bytes:
        raise ValueError("Provider catalog response exceeds the configured size limit")
    try:
        text = bytes(payload).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Provider catalog response is not UTF-8") from error
    return ProviderCatalog.from_json_text(text), text


class ProviderCatalogCache:
    """Persist only catalog snapshots that already passed transport and schema validation."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or default_catalog_cache_path()).expanduser()

    def load(self) -> ProviderCatalog | None:
        if not self.path.is_file():
            return None
        try:
            return ProviderCatalog.from_file(self.path)
        except (OSError, UnicodeError, ValueError):
            return None

    def store(self, text: str) -> ProviderCatalog:
        catalog = ProviderCatalog.from_json_text(text)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(text)
                if text and not text.endswith("\n"):
                    output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.path)
        except Exception:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise
        return catalog

    def refresh(
        self,
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
        timeout: float = _DEFAULT_TIMEOUT,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        opener: Callable[..., object] = urlopen,
    ) -> ProviderCatalog:
        catalog, text = fetch_provider_catalog(
            url,
            allowed_hosts=allowed_hosts,
            timeout=timeout,
            max_bytes=max_bytes,
            opener=opener,
        )
        self.store(text)
        return catalog


__all__ = [
    "ProviderCatalogCache",
    "default_catalog_cache_path",
    "fetch_provider_catalog",
]
