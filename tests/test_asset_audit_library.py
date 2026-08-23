import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.archive.audit import (
    DEFAULT_REPORT_NAME,
    audit_asset_references,
    collect_asset_audit,
    docx_asset_references,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = PROJECT_ROOT / "audit_asset_references.py"


def write_conversation_with_active_dictation(path: Path) -> None:
    conversation = {
        "conversation_id": "audit-conversation-001",
        "title": "Audit Library Fixture",
        "current_node": "node-assistant",
        "mapping": {
            "node-user": {
                "id": "node-user",
                "parent": None,
                "children": ["node-assistant"],
                "message": {
                    "id": "message-user",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["hello"]},
                    "metadata": {},
                },
            },
            "node-assistant": {
                "id": "node-assistant",
                "parent": "node-user",
                "children": [],
                "message": {
                    "id": "message-assistant",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["reply"]},
                    "metadata": {
                        "dictation_asset_pointer": "file_dictation",
                        "dictation_asset_format": "wav",
                    },
                },
            },
        },
    }
    raw = (json.dumps(conversation, indent=2) + "\n").encode("utf-8")
    with lzma.open(path, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
        handle.write(raw)


def create_synthetic_archive(root: Path) -> None:
    attachment = root / "assets" / "attachment"
    dictation = root / "assets" / "dictation"
    image = root / "assets" / "image"
    markdown = root / "markdown"
    downloads = root / "downloads"
    for directory in (attachment, dictation, image, markdown, downloads):
        directory.mkdir(parents=True, exist_ok=True)

    (image / "file_rendered__image.png").write_bytes(b"rendered")
    (dictation / "file_dictation__audio.wav").write_bytes(b"dictation")

    (attachment / "file_shared__copy.bin").write_bytes(b"same bytes")
    (dictation / "file_shared__audio.bin").write_bytes(b"same bytes")

    (attachment / "file_conflict__a.bin").write_bytes(b"first")
    (attachment / "file_conflict__b.bin").write_bytes(b"second")

    (attachment / "readme.txt").write_bytes(b"unidentified")

    (markdown / "conversation.md").write_text(
        "Rendered marker: Asset ID: `file_rendered`\n"
        "[missing](../assets/attachment/file_missing__missing.bin)\n",
        encoding="utf-8",
    )
    write_conversation_with_active_dictation(
        downloads / "audit-conversation.json.xz"
    )


def create_minimal_docx(path: Path) -> None:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Asset ID: file_docxtext</w:t></w:r></w:p>
  </w:body>
</w:document>
"""
    relationships_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="test" Target="../assets/attachment/file_docxlink__item.bin" TargetMode="External"/>
</Relationships>
"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", relationships_xml)


class AssetAuditLibraryTests(unittest.TestCase):
    def test_collect_asset_audit_preserves_v28_classifications_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)
            create_synthetic_archive(archive_root)

            report = collect_asset_audit(archive_root)

        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["audit_version"], "v2.7")
        self.assertEqual(report["asset_files_scanned"], 7)
        self.assertEqual(report["unique_local_asset_ids"], 4)
        self.assertEqual(report["markdown_files_scanned"], 1)
        self.assertEqual(report["referenced_asset_ids"], 2)
        self.assertEqual(report["unreferenced_local_asset_count"], 3)
        self.assertEqual(report["referenced_missing_local_count"], 1)
        self.assertEqual(report["duplicate_local_asset_id_count"], 2)
        self.assertEqual(report["unidentified_local_asset_file_count"], 1)
        self.assertEqual(
            report["duplicate_local_asset_content_status_counts"],
            {"identical": 1, "conflicting": 1, "unreadable": 0},
        )
        self.assertEqual(
            report["duplicate_local_asset_kind_counts"],
            {"attachment_filename_variant": 1, "dictation_mirror": 1},
        )
        self.assertEqual(
            report["unreferenced_category_counts"],
            {"dictation_source_active": 1, "unexplained": 2},
        )

        duplicate_by_id = {
            item["file_id"]: item
            for item in report["duplicate_local_asset_ids"]
        }
        self.assertEqual(
            duplicate_by_id["file_shared"]["content_status"],
            "identical",
        )
        self.assertEqual(
            duplicate_by_id["file_shared"]["kind"],
            "dictation_mirror",
        )
        self.assertEqual(
            duplicate_by_id["file_conflict"]["content_status"],
            "conflicting",
        )
        self.assertEqual(
            duplicate_by_id["file_conflict"]["kind"],
            "attachment_filename_variant",
        )

    def test_audit_asset_references_writes_v28_compressed_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)
            create_synthetic_archive(archive_root)

            result = audit_asset_references(archive_root)

            self.assertEqual(result.report_path.name, DEFAULT_REPORT_NAME)
            self.assertTrue(result.report_path.is_file())
            with lzma.open(result.report_path, "rt", encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(persisted, result.report)

    def test_docx_reference_scanner_preserves_marker_and_relationship_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            docx_path = Path(temporary_directory) / "fixture.docx"
            create_minimal_docx(docx_path)

            references = docx_asset_references(docx_path)

        self.assertEqual(references, {"file_docxtext", "file_docxlink"})

    def test_legacy_cli_strict_exit_code_and_report_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory) / "archive"
            archive_root.mkdir()
            create_synthetic_archive(archive_root)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(AUDIT_SCRIPT),
                    "--archive-root",
                    str(archive_root),
                    "--strict",
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            self.assertIn("Asset reference audit", completed.stdout)
            self.assertIn("Unreferenced local assets  : 3", completed.stdout)
            self.assertIn("Duplicate local asset IDs  : 2", completed.stdout)
            self.assertIn("content-conflicting      : 1", completed.stdout)
            self.assertTrue(
                (archive_root / "reports" / DEFAULT_REPORT_NAME).is_file()
            )

    def test_library_import_has_no_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.archive.audit"],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertFalse((profile / "Documents" / "ChatGPT Archive").exists())


if __name__ == "__main__":
    unittest.main()
