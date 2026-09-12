from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.provider_catalog import ProviderCatalog


class ProviderCatalogTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "schema_version": 1,
            "catalog_id": "msne-official",
            "generated_at": "2026-09-12T20:00:00Z",
            "providers": [
                {
                    "provider_id": "chatgpt",
                    "display_name": "ChatGPT",
                    "distribution_name": "export-provider-chatgpt",
                    "version": "0.2.0",
                    "provider_api_version": 1,
                    "min_msne_version": "2.10.0",
                    "artifact_url": "https://example.invalid/export_provider_chatgpt-0.2.0-py3-none-any.whl",
                    "sha256": "a" * 64,
                    "capabilities": ["collect", "browse"],
                    "description": "ChatGPT archive provider",
                }
            ],
        }

    def test_parses_catalog_and_detects_update(self) -> None:
        catalog = ProviderCatalog.from_json_text(json.dumps(self._payload()))
        self.assertEqual(catalog.catalog_id, "msne-official")
        self.assertEqual(len(catalog.entries), 1)
        entry = catalog.entries[0]
        self.assertTrue(entry.compatible_provider_api)
        self.assertTrue(entry.supports_msne("2.10.0"))
        self.assertTrue(entry.supports_msne("2.11.0"))
        self.assertFalse(entry.supports_msne("2.9.9"))
        self.assertTrue(entry.is_update_for("0.1.0"))
        self.assertFalse(entry.is_update_for("0.2.0"))

    def test_rejects_non_https_artifact_url(self) -> None:
        payload = self._payload()
        payload["providers"][0]["artifact_url"] = "http://example.invalid/provider.whl"
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            ProviderCatalog.from_json_text(json.dumps(payload))

    def test_rejects_invalid_sha256(self) -> None:
        payload = self._payload()
        payload["providers"][0]["sha256"] = "not-a-digest"
        with self.assertRaisesRegex(ValueError, "invalid SHA-256"):
            ProviderCatalog.from_json_text(json.dumps(payload))

    def test_rejects_invalid_schema_type(self) -> None:
        payload = self._payload()
        payload["schema_version"] = []
        with self.assertRaisesRegex(ValueError, "Invalid provider catalog schema version"):
            ProviderCatalog.from_json_text(json.dumps(payload))

    def test_rejects_duplicate_provider_id(self) -> None:
        payload = self._payload()
        duplicate = dict(payload["providers"][0])
        duplicate["distribution_name"] = "export-provider-chatgpt-copy"
        payload["providers"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate catalog provider_id"):
            ProviderCatalog.from_json_text(json.dumps(payload))

    def test_rejects_duplicate_distribution_after_normalization(self) -> None:
        payload = self._payload()
        duplicate = dict(payload["providers"][0])
        duplicate["provider_id"] = "chatgpt-copy"
        duplicate["distribution_name"] = "export_provider_chatgpt"
        payload["providers"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Duplicate catalog distribution"):
            ProviderCatalog.from_json_text(json.dumps(payload))

    def test_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "catalog.json"
            path.write_text(json.dumps(self._payload()), encoding="utf-8")
            catalog = ProviderCatalog.from_file(path)
        self.assertEqual(catalog.entries[0].provider_id, "chatgpt")


if __name__ == "__main__":
    unittest.main()
