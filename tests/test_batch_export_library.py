import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.export.batch import export_batch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class BatchExportLibraryTests(unittest.TestCase):
    def _write_conversation(
        self,
        archive_root: Path,
        *,
        filename: str = "synthetic.json",
        conversation_id: str = "conv-batch-001",
        text: str = "Synthetic batch answer",
    ) -> Path:
        downloads = archive_root / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        conversation = {
            "title": "Synthetic batch export",
            "conversation_id": conversation_id,
            "create_time": 1_700_000_000.0,
            "update_time": 1_700_000_100.0,
            "current_node": "assistant",
            "mapping": {
                "root": {
                    "id": "root",
                    "parent": None,
                    "children": ["user"],
                    "message": None,
                },
                "user": {
                    "id": "user",
                    "parent": "root",
                    "children": ["assistant"],
                    "message": {
                        "id": "message-user",
                        "author": {"role": "user"},
                        "create_time": 1_700_000_010.0,
                        "update_time": None,
                        "content": {
                            "content_type": "text",
                            "parts": ["Synthetic batch question"],
                        },
                        "metadata": {},
                    },
                },
                "assistant": {
                    "id": "assistant",
                    "parent": "user",
                    "children": [],
                    "message": {
                        "id": "message-assistant",
                        "author": {"role": "assistant"},
                        "create_time": 1_700_000_020.0,
                        "update_time": None,
                        "content": {
                            "content_type": "text",
                            "parts": [text],
                        },
                        "metadata": {},
                    },
                },
            },
        }
        path = downloads / filename
        path.write_text(
            json.dumps(conversation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def test_end_to_end_batch_uses_library_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(archive_root)
            progress: list[str] = []

            result = export_batch(
                archive_root=archive_root,
                keep_markdown=True,
                progress=progress.append,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.requested, 1)
            self.assertEqual(result.markdown_converted, 1)
            self.assertEqual(result.docx_converted, 1)
            self.assertEqual(result.markdown_failed, ())
            self.assertEqual(result.docx_failed, ())
            self.assertTrue((archive_root / "markdown" / "synthetic.md").is_file())
            self.assertTrue((archive_root / "synthetic.docx").is_file())
            self.assertIsNotNone(result.audit_result)
            self.assertTrue(result.audit_result.report_path.is_file())
            self.assertIn("Using Markdown export library in-process.", progress)
            self.assertIn("Using DOCX export library in-process.", progress)

    def test_persistent_markdown_skip_semantics_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(archive_root)
            markdown_directory = archive_root / "markdown"
            markdown_directory.mkdir(parents=True)
            markdown_path = markdown_directory / "synthetic.md"
            markdown_path.write_text("# Existing\n", encoding="utf-8")

            result = export_batch(
                archive_root=archive_root,
                keep_markdown=True,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.markdown_converted, 0)
            self.assertEqual(result.markdown_skipped, 1)
            self.assertEqual(markdown_path.read_text(encoding="utf-8"), "# Existing\n")
            self.assertTrue((archive_root / "synthetic.docx").is_file())

    def test_failed_docx_preserves_temporary_markdown_for_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(archive_root)

            with mock.patch(
                "gpt_exporter.export.batch.export_docx",
                side_effect=RuntimeError("synthetic DOCX failure"),
            ):
                result = export_batch(archive_root=archive_root)

            try:
                self.assertFalse(result.success)
                self.assertFalse(result.temporary_markdown_removed)
                self.assertTrue(result.markdown_directory.is_dir())
                self.assertTrue((result.markdown_directory / "synthetic.md").is_file())
                self.assertEqual(len(result.docx_failed), 1)
                self.assertIsNone(result.audit_result)
            finally:
                shutil.rmtree(result.markdown_directory, ignore_errors=True)

    def test_library_call_does_not_mutate_sys_argv_or_require_script_loading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(archive_root)
            original = sys.argv[:]

            result = export_batch(
                archive_root=archive_root,
                markdown_only=True,
            )

            self.assertTrue(result.success)
            self.assertEqual(sys.argv, original)

        source = (REPOSITORY_ROOT / "export_all.py").read_text(encoding="utf-8")
        self.assertNotIn("importlib.util", source)
        self.assertNotIn("spec_from_file_location", source)
        self.assertNotIn("sys.argv =", source)
        self.assertIn("export_batch", source)

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary

            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.export.batch"],
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertFalse(
                (Path(temporary) / "Documents" / "ChatGPT Archive").exists()
            )


if __name__ == "__main__":
    unittest.main()
