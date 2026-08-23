import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.archive.inventory import (
    collect_media_inventory,
    inventory_media,
    render_console_summary,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCRIPT = PROJECT_ROOT / "inventory_media.py"


def synthetic_conversation() -> dict:
    return {
        "conversation_id": "conv-inventory-001",
        "title": "Inventory Fixture",
        "current_node": "node-1",
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": [],
                "message": {
                    "id": "message-1",
                    "author": {"role": "user"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "sediment://file-image",
                            },
                            {
                                "content_type": "file_asset_pointer",
                                "file_id": "file-content",
                            },
                            {
                                "content_type": "audio_asset_pointer",
                                "asset_pointer": "sediment://file-audio",
                            },
                        ],
                    },
                    "metadata": {
                        "dictation_asset_pointer": "sediment://file-dictation",
                        "dictation_asset_format": "M4A",
                        "attachments": [
                            {
                                "file_id": "file-attachment",
                                "mime_type": "application/pdf",
                                "name": "notes.pdf",
                            }
                        ],
                    },
                },
            }
        },
    }


def write_xz_conversation(path: Path) -> None:
    raw = (
        json.dumps(synthetic_conversation(), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    with lzma.open(path, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
        handle.write(raw)


class InventoryLibraryTests(unittest.TestCase):
    def test_collect_media_inventory_preserves_v28_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            downloads = Path(temporary_directory) / "downloads"
            downloads.mkdir()
            conversation = downloads / "fixture.json.xz"
            write_xz_conversation(conversation)

            progress: list[str] = []
            report = collect_media_inventory(downloads, progress=progress.append)

        self.assertEqual(progress, ["[1/1] fixture.json.xz"])
        self.assertEqual(
            report["summary"],
            {
                "dictation_assets": 1,
                "attachment_records": 1,
                "image_asset_pointers": 1,
                "file_asset_pointers": 1,
                "audio_asset_pointers": 1,
            },
        )
        self.assertEqual(
            report["pointer_kinds"],
            {
                "dictation_asset_pointer": 1,
                "attachment:file_id": 1,
                "file_id": 2,
                "asset_pointer": 2,
            },
        )
        self.assertEqual(
            report["pointer_schemes"],
            {"sediment": 3, "no-scheme": 3},
        )
        self.assertEqual(report["dictation_formats"], {"m4a": 1})
        self.assertEqual(report["attachment_mime_types"], {"application/pdf": 1})
        self.assertEqual(report["attachment_extensions"], {".pdf": 1})
        self.assertEqual(
            report["attachment_fields"],
            {"file_id": 1, "mime_type": 1, "name": 1},
        )
        self.assertEqual(
            report["per_file"],
            [
                {
                    "filename": "fixture.json.xz",
                    "title": "Inventory Fixture",
                    "image_asset_pointers": 1,
                    "file_asset_pointers": 1,
                    "audio_asset_pointers": 1,
                    "dictation_assets": 1,
                    "attachment_records": 1,
                }
            ],
        )

    def test_inventory_media_writes_verified_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            downloads = root / "downloads"
            reports = root / "reports"
            downloads.mkdir()
            write_xz_conversation(downloads / "fixture.json.xz")
            legacy_json = reports / "inventory-media-report.json"
            reports.mkdir()
            legacy_json.write_text("legacy", encoding="utf-8")

            result = inventory_media(downloads, reports)

            self.assertTrue(result.text_report_path.is_file())
            self.assertTrue(result.json_report_path.is_file())
            self.assertFalse(legacy_json.exists())
            with lzma.open(result.json_report_path, "rt", encoding="utf-8") as handle:
                stored_report = json.load(handle)
            self.assertEqual(stored_report, result.report)
            text = result.text_report_path.read_text(encoding="utf-8")
            self.assertIn("Images      : 1", text)
            self.assertIn("application/pdf: 1", text)
            self.assertIn("fixture.json.xz", text)
            summary = render_console_summary(result)
            self.assertIn("Media inventory complete", summary)
            self.assertIn(f"Text report : {result.text_report_path}", summary)

    def test_library_import_has_no_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)

            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.archive.inventory"],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            archive_root = profile / "Documents" / "ChatGPT Archive"
            self.assertFalse(archive_root.exists())
            self.assertEqual(completed.stdout, "")

    def test_legacy_cli_uses_library_and_preserves_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            archive_root = profile / "Documents" / "ChatGPT Archive"
            downloads = archive_root / "downloads"
            downloads.mkdir(parents=True)
            write_xz_conversation(downloads / "fixture.json.xz")

            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = subprocess.run(
                [sys.executable, str(INVENTORY_SCRIPT)],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("[1/1] fixture.json.xz", completed.stdout)
            self.assertIn("Media inventory complete", completed.stdout)
            self.assertIn("Images      : 1", completed.stdout)
            self.assertTrue((archive_root / "reports" / "inventory-media-report.txt").is_file())
            self.assertTrue((archive_root / "reports" / "inventory-media-report.json.xz").is_file())


if __name__ == "__main__":
    unittest.main()
