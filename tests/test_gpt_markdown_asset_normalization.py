from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from gpt_exporter.providers.gpt.export.markdown import (
    _normalize_asset_metadata_from_canonical_paths,
)


class GptMarkdownAssetNormalizationTests(unittest.TestCase):
    def test_canonical_image_bucket_repairs_stale_attachment_webp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "assets"
            image = root / "image" / "file_123__photo.webp"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"webp-placeholder")

            asset = SimpleNamespace(
                filename="image/file_123__photo.webp",
                kind="attachment",
                content_type="application/octet-stream",
            )
            implementation = SimpleNamespace(
                infer_local_content_type=lambda path: (
                    "image/webp" if Path(path).suffix.casefold() == ".webp" else None
                )
            )

            _normalize_asset_metadata_from_canonical_paths(
                {"file_123": asset},
                root,
                implementation,
            )

            self.assertEqual(asset.kind, "image")
            self.assertEqual(asset.content_type, "image/webp")

    def test_canonical_external_bucket_keeps_external_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "assets"
            asset = SimpleNamespace(
                filename="external/external_123__preview.jpg",
                kind="attachment",
                content_type=None,
            )
            implementation = SimpleNamespace(
                infer_local_content_type=lambda path: "image/jpeg"
            )

            _normalize_asset_metadata_from_canonical_paths(
                {"external_123": asset},
                root,
                implementation,
            )

            self.assertEqual(asset.kind, "external_image")
            self.assertEqual(asset.content_type, "image/jpeg")


if __name__ == "__main__":
    unittest.main()
