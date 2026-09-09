from __future__ import annotations

import json
import lzma
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.assets import asset_bucket
from gpt_exporter.providers.gpt.assets import migrate_gpt_asset_layout


class SharedAssetBucketTests(unittest.TestCase):
    def test_semantic_kinds_map_to_canonical_buckets(self) -> None:
        self.assertEqual(asset_bucket("attachment", "application/pdf"), "attachment")
        self.assertEqual(asset_bucket("dictation", "audio/mp4"), "dictation")
        self.assertEqual(asset_bucket("image", "image/png"), "image")
        self.assertEqual(asset_bucket("generated-image", "image/webp"), "image")
        self.assertEqual(asset_bucket("external_image", "image/jpeg"), "external")
        self.assertEqual(asset_bucket("external-preview", "image/jpeg"), "external")
        self.assertEqual(asset_bucket("author-avatar", "image/webp"), "external")


class GptAssetLayoutMigrationTests(unittest.TestCase):
    def _write_xz_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        with lzma.open(path, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(raw)

    def test_migrates_registry_assets_by_conversation_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attachment = root / "assets" / "attachment"
            attachment.mkdir(parents=True)

            ids = {
                "attachment": "file_attach123",
                "dictation": "file_dictate123",
                "image": "file_image123",
                "external": "external_0123456789abcdef",
            }
            for label, file_id in ids.items():
                (attachment / f"{file_id}__{label}.bin").write_bytes(label.encode("ascii"))

            conversation = {
                "mapping": {
                    "a": {
                        "message": {
                            "metadata": {
                                "attachments": [{"id": ids["attachment"], "name": "manual.pdf"}],
                                "dictation_asset_pointer": f"sediment://{ids['dictation']}",
                                "_archive_external_images": [
                                    {"asset_id": ids["external"], "source_url": "https://example.test/thumb.jpg"}
                                ],
                            },
                            "content": {
                                "content_type": "multimodal_text",
                                "parts": [
                                    {
                                        "content_type": "image_asset_pointer",
                                        "asset_pointer": f"sediment://{ids['image']}",
                                    }
                                ],
                            },
                        }
                    }
                }
            }
            self._write_xz_json(root / "downloads" / "conversation.json.xz", conversation)

            registry = {
                "generated_at": "2026-09-09T10:00:00+02:00",
                "registry_mode": "cumulative",
                "results": [
                    {
                        "kind": "attachment",
                        "file_id": file_id,
                        "status": "downloaded",
                        "filename": f"attachment/{file_id}__{label}.bin",
                        "content_type": "application/octet-stream",
                    }
                    for label, file_id in ids.items()
                ],
            }
            registry_path = root / "reports" / "asset-download-index-v2.json.xz"
            self._write_xz_json(registry_path, registry)

            result = migrate_gpt_asset_layout(root)

            self.assertEqual(result.moved, 3)
            self.assertEqual(result.unchanged, 1)
            self.assertTrue((root / "assets" / "attachment" / f"{ids['attachment']}__attachment.bin").is_file())
            self.assertTrue((root / "assets" / "dictation" / f"{ids['dictation']}__dictation.bin").is_file())
            self.assertTrue((root / "assets" / "image" / f"{ids['image']}__image.bin").is_file())
            self.assertTrue((root / "assets" / "external" / f"{ids['external']}__external.bin").is_file())

            with lzma.open(registry_path, "rt", encoding="utf-8") as handle:
                migrated_registry = json.load(handle)
            paths = {
                item["file_id"]: item["filename"]
                for item in migrated_registry["results"]
            }
            self.assertEqual(paths[ids["attachment"]], f"attachment/{ids['attachment']}__attachment.bin")
            self.assertEqual(paths[ids["dictation"]], f"dictation/{ids['dictation']}__dictation.bin")
            self.assertEqual(paths[ids["image"]], f"image/{ids['image']}__image.bin")
            self.assertEqual(paths[ids["external"]], f"external/{ids['external']}__external.bin")

    def test_existing_identical_destination_is_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "assets" / "attachment" / "external_deadbeef__thumb.jpg"
            destination = root / "assets" / "external" / source.name
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"same")
            destination.write_bytes(b"same")

            registry_path = root / "reports" / "asset-download-index-v2.json.xz"
            self._write_xz_json(
                registry_path,
                {
                    "results": [
                        {
                            "kind": "external_image",
                            "file_id": "external_deadbeef",
                            "status": "downloaded",
                            "filename": f"attachment/{source.name}",
                            "content_type": "image/jpeg",
                        }
                    ]
                },
            )

            result = migrate_gpt_asset_layout(root)

            self.assertEqual(result.reused, 1)
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_bytes(), b"same")


if __name__ == "__main__":
    unittest.main()
