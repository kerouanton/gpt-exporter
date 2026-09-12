from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.provider_catalog_transport import (
    ProviderCatalogCache,
    fetch_provider_catalog,
)


class _Response:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.payload = payload
        self.final_url = final_url
        self.closed = False

    def geturl(self) -> str:
        return self.final_url

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]

    def close(self) -> None:
        self.closed = True


class ProviderCatalogTransportTests(unittest.TestCase):
    def _payload(self) -> bytes:
        return json.dumps(
            {
                "schema_version": 1,
                "catalog_id": "msne-test",
                "generated_at": "2026-09-12T20:00:00Z",
                "providers": [
                    {
                        "provider_id": "discord",
                        "display_name": "Discord",
                        "distribution_name": "export-provider-discord",
                        "version": "0.2.0",
                        "provider_api_version": 1,
                        "min_msne_version": "2.10.0",
                        "artifact_url": "https://downloads.example.test/discord.whl",
                        "sha256": "c" * 64,
                    }
                ],
            }
        ).encode("utf-8")

    def test_fetch_accepts_pinned_https_origin(self) -> None:
        response = _Response(self._payload(), "https://catalog.example.test/providers.json")

        def opener(_request, *, timeout):
            self.assertEqual(timeout, 3.0)
            return response

        catalog, text = fetch_provider_catalog(
            "https://catalog.example.test/providers.json",
            allowed_hosts=("catalog.example.test",),
            timeout=3.0,
            opener=opener,
        )
        self.assertEqual(catalog.entries[0].provider_id, "discord")
        self.assertIn("msne-test", text)
        self.assertTrue(response.closed)

    def test_fetch_rejects_untrusted_initial_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "host is not trusted"):
            fetch_provider_catalog(
                "https://evil.example.test/providers.json",
                allowed_hosts=("catalog.example.test",),
                opener=lambda *_args, **_kwargs: None,
            )

    def test_fetch_rejects_redirect_to_untrusted_host(self) -> None:
        response = _Response(self._payload(), "https://evil.example.test/providers.json")
        with self.assertRaisesRegex(ValueError, "host is not trusted"):
            fetch_provider_catalog(
                "https://catalog.example.test/providers.json",
                allowed_hosts=("catalog.example.test",),
                opener=lambda *_args, **_kwargs: response,
            )
        self.assertTrue(response.closed)

    def test_fetch_rejects_oversized_response(self) -> None:
        response = _Response(b"x" * 101, "https://catalog.example.test/providers.json")
        with self.assertRaisesRegex(ValueError, "size limit"):
            fetch_provider_catalog(
                "https://catalog.example.test/providers.json",
                allowed_hosts=("catalog.example.test",),
                max_bytes=100,
                opener=lambda *_args, **_kwargs: response,
            )

    def test_cache_round_trip_and_invalid_cache_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            cache = ProviderCatalogCache(path)
            text = self._payload().decode("utf-8")
            stored = cache.store(text)
            self.assertEqual(stored.catalog_id, "msne-test")
            loaded = cache.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.entries[0].version, "0.2.0")
            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(cache.load())

    def test_refresh_stores_only_validated_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cache = ProviderCatalogCache(Path(temporary) / "catalog.json")
            response = _Response(self._payload(), "https://catalog.example.test/providers.json")
            catalog = cache.refresh(
                "https://catalog.example.test/providers.json",
                allowed_hosts=("catalog.example.test",),
                opener=lambda *_args, **_kwargs: response,
            )
            self.assertEqual(catalog.catalog_id, "msne-test")
            self.assertTrue(cache.path.is_file())


if __name__ == "__main__":
    unittest.main()
