import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.validation import _docx_fingerprint


_RELATIONSHIPS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    Target="{target}"
    TargetMode="External"/>
</Relationships>
"""


class DocxValidationFingerprintTests(unittest.TestCase):
    def _write_docx(self, path: Path, target: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "<document>same content</document>")
            archive.writestr(
                "word/_rels/document.xml.rels",
                _RELATIONSHIPS_TEMPLATE.format(target=target),
            )

    def test_relative_relationships_resolving_to_same_asset_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            asset = root / "assets" / "file_abc.txt"
            asset.parent.mkdir(parents=True)
            asset.write_text("asset", encoding="utf-8")

            production = root / "production.docx"
            oracle = root / "reports" / "oracle.docx"
            self._write_docx(production, ".\\assets\\file_abc.txt")
            self._write_docx(oracle, "..\\assets\\file_abc.txt")

            self.assertEqual(
                _docx_fingerprint(production),
                _docx_fingerprint(oracle),
            )

    def test_relationships_resolving_to_different_assets_do_not_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            (root / "assets").mkdir(parents=True)
            (root / "assets" / "file_abc.txt").write_text("a", encoding="utf-8")
            (root / "assets" / "file_other.txt").write_text("b", encoding="utf-8")

            production = root / "production.docx"
            oracle = root / "reports" / "oracle.docx"
            self._write_docx(production, ".\\assets\\file_abc.txt")
            self._write_docx(oracle, "..\\assets\\file_other.txt")

            self.assertNotEqual(
                _docx_fingerprint(production),
                _docx_fingerprint(oracle),
            )


if __name__ == "__main__":
    unittest.main()
