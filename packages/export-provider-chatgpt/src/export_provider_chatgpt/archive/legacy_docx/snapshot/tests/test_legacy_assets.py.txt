import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import hashlib
import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image

from gpt_exporter.legacy.assets import extract_legacy_assets


class LegacyAssetExportTests(unittest.TestCase):
    def test_extracts_inline_image_with_word_block_order_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "fixture.png"
            Image.new("RGB", (12, 8), "white").save(image_path)

            source = root / "HAM GPT 2026-04-03 Media.docx"
            document = Document()
            paragraph = document.add_paragraph("before image")
            paragraph.add_run().add_picture(str(image_path))
            document.save(source)

            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            result = extract_legacy_assets(
                source,
                root / "assets",
                source_sha256=source_sha,
            )

            self.assertEqual(result.image_count, 1)
            self.assertEqual(result.attachment_count, 0)
            self.assertEqual(result.unresolved_relationships, ())
            asset = result.assets[0]
            self.assertEqual(asset.block_order, 0)
            self.assertEqual(asset.kind, "image")
            self.assertTrue(asset.output_path.is_file())
            self.assertEqual(hashlib.sha256(asset.output_path.read_bytes()).hexdigest(), asset.sha256)
            self.assertIn(source_sha[:16], str(asset.output_path))

    def test_repeated_reference_writes_one_content_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "fixture.png"
            Image.new("RGB", (10, 10), "white").save(image_path)

            source = root / "PKI GPT 2026-04-03 Repeated.docx"
            document = Document()
            document.add_paragraph("first").add_run().add_picture(str(image_path))
            document.add_paragraph("second").add_run().add_picture(str(image_path))
            document.save(source)

            source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
            result = extract_legacy_assets(
                source,
                root / "assets",
                source_sha256=source_sha,
            )

            self.assertEqual(result.image_count, 2)
            self.assertEqual(len({asset.output_path for asset in result.assets}), 1)
            self.assertEqual([asset.block_order for asset in result.assets], [0, 1])


if __name__ == "__main__":
    unittest.main()
