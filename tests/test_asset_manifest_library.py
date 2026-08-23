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

from gpt_exporter.archive.manifest import (
    NoConversationFilesError,
    build_asset_manifest,
    collect_asset_manifest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCRIPT = PROJECT_ROOT / "build_asset_manifest.py"


def synthetic_conversation() -> dict[str, object]:
    return {
        "conversation_id": "manifest-conversation-001",
        "title": "Manifest Library Fixture",
        "current_node": "node-2",
        "mapping": {
            "node-1": {
                "id": "node-1",
                "parent": None,
                "children": ["node-2"],
                "message": {
                    "id": "message-1",
                    "metadata": {
                        "dictation_asset_pointer": "file-dictation-001",
                        "dictation_asset_format": "WAV",
                        "attachments": [
                            {
                                "id": "file-attachment-001",
                                "name": "document.pdf",
                                "size": 1234,
                                "mime_type": "application/pdf",
                            }
                        ],
                    },
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "file-image-001",
                                "width": 640,
                                "height": 480,
                                "size_bytes": 4321,
                            }
                        ],
                    },
                },
            },
            "node-2": {
                "id": "node-2",
                "parent": "node-1",
                "children": [],
                "message": {
                    "id": "message-2",
                    "metadata": {
                        "dictation_asset_pointer": "file-dictation-001",
                        "dictation_asset_format": "WAV",
                        "attachments": [
                            {
                                "id": "file-attachment-001",
                                "name": "document.pdf",
                                "size": 1234,
                                "mime_type": "application/pdf",
                            },
                            {
                                "library_file_id": "library-file-002",
                                "name": "picture.png",
                                "size": 987,
                                "mimeType": "image/png",
                            },
                        ],
                    },
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "file-image-001",
                                "width": 640,
                                "height": 480,
                                "size_bytes": 4321,
                            }
                        ],
                    },
                },
            },
        },
    }


def write_xz_conversation(path: Path) -> None:
    raw = (
        json.dumps(synthetic_conversation(), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    with lzma.open(path, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
        handle.write(raw)


class AssetManifestLibraryTests(unittest.TestCase):
    def test_collect_asset_manifest_preserves_v28_unique_and_raw_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            downloads = Path(temporary_directory) / "downloads"
            downloads.mkdir()
            write_xz_conversation(downloads / "conversation.json.xz")

            progress: list[str] = []
            manifest = collect_asset_manifest(downloads, progress=progress.append)

        summary = manifest["summary"]
        self.assertEqual(summary["conversation_files"], 1)
        self.assertEqual(summary["unique_images"], 1)
        self.assertEqual(summary["unique_dictations"], 1)
        self.assertEqual(summary["unique_attachments"], 2)
        self.assertEqual(summary["raw_image_pointer_occurrences"], 2)
        self.assertEqual(summary["raw_dictation_pointer_occurrences"], 2)
        self.assertEqual(summary["raw_attachment_occurrences"], 3)
        self.assertEqual(
            manifest["attachment_mime_types"],
            {"application/pdf": 1, "image/png": 1},
        )
        self.assertEqual(
            manifest["attachment_extensions"],
            {".pdf": 1, ".png": 1},
        )
        self.assertEqual(progress, ["[1/1] conversation.json.xz"])

    def test_build_asset_manifest_writes_verified_v28_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)
            downloads = archive_root / "downloads"
            reports = archive_root / "reports"
            downloads.mkdir()
            write_xz_conversation(downloads / "conversation.json.xz")

            result = build_asset_manifest(downloads, reports)

            self.assertEqual(result.json_manifest_path.name, "asset-manifest.json.xz")
            self.assertEqual(result.text_manifest_path.name, "asset-manifest.txt")
            with lzma.open(result.json_manifest_path, "rt", encoding="utf-8") as handle:
                persisted = json.load(handle)
            self.assertEqual(persisted, result.manifest)

            text = result.text_manifest_path.read_text(encoding="utf-8")
            self.assertIn("ChatGPT Asset Manifest", text)
            self.assertIn("Unique images                  : 1", text)
            self.assertIn("Raw attachment occurrences     : 3", text)
            self.assertIn("application/pdf: 1", text)
            self.assertIn(".png: 1", text)

    def test_no_conversation_files_preserves_v28_reports_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)
            downloads = archive_root / "downloads"
            reports = archive_root / "reports"
            downloads.mkdir()

            with self.assertRaises(NoConversationFilesError):
                build_asset_manifest(downloads, reports)

            self.assertTrue(reports.is_dir())

    def test_legacy_cli_uses_library_and_preserves_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            archive_root = profile / "Documents" / "ChatGPT Archive"
            downloads = archive_root / "downloads"
            downloads.mkdir(parents=True)
            write_xz_conversation(downloads / "conversation.json.xz")

            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = subprocess.run(
                [sys.executable, str(MANIFEST_SCRIPT)],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("[1/1] conversation.json.xz", completed.stdout)
            self.assertIn("Asset manifest complete", completed.stdout)
            self.assertTrue((archive_root / "reports" / "asset-manifest.json.xz").is_file())
            self.assertTrue((archive_root / "reports" / "asset-manifest.txt").is_file())

    def test_library_import_has_no_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import gpt_exporter.archive.manifest",
                ],
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
