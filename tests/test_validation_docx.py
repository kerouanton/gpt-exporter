import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from gpt_exporter.validation import _compare_export_oracle, _docx_fingerprint


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

    def test_export_oracle_generates_both_docx_sides_in_validation_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            oracle_root = root / "reports" / "provider-validation" / "chatgpt" / "export-oracle"
            source = root / "downloads" / "conversation.json.xz"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source")

            provider = mock.Mock()
            provider.normalize_conversation.return_value = mock.sentinel.conversation

            def write_core(_conversation, output_path, *, overwrite=False):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text("same markdown\n", encoding="utf-8")

            def write_legacy(_source, output_path, **_kwargs):
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text("same markdown\n", encoding="utf-8")

            generated_docx: list[Path] = []

            def write_docx(_markdown_path, output_path, *, overwrite=False):
                path = Path(output_path)
                path.write_bytes(b"placeholder")
                generated_docx.append(path)

            with (
                mock.patch("gpt_exporter.validation.export_normalized_conversation", side_effect=write_core),
                mock.patch("gpt_exporter.validation.export_markdown", side_effect=write_legacy),
                mock.patch("gpt_exporter.validation.export_docx", side_effect=write_docx),
                mock.patch("gpt_exporter.validation._docx_fingerprint", return_value=(("same", "digest"),)),
                mock.patch("gpt_exporter.validation.legacy_indexer.find_docx", side_effect=AssertionError("production DOCX must not be consulted")),
            ):
                markdown_matches, _, docx_matches, _ = _compare_export_oracle(
                    provider,
                    source,
                    archive=root,
                    oracle_root=oracle_root,
                    conversation_id="conv-001",
                )

            self.assertTrue(markdown_matches)
            self.assertTrue(docx_matches)
            self.assertEqual(
                generated_docx,
                [
                    oracle_root / "conv-001-core.docx",
                    oracle_root / "conv-001-legacy.docx",
                ],
            )


if __name__ == "__main__":
    unittest.main()
