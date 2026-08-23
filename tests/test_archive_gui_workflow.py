import os
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import archive_gui_workflow as workflow


class ArchiveGuiWorkflowTests(unittest.TestCase):
    def test_find_latest_source_bundle_returns_newest_non_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as first_name, tempfile.TemporaryDirectory() as second_name:
            first = Path(first_name)
            second = Path(second_name)
            older = first / workflow.SOURCE_BUNDLE_NAME
            newer = second / workflow.SOURCE_BUNDLE_NAME
            older.write_text("older", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("newer", encoding="utf-8")

            found = workflow.find_latest_source_bundle([first, second])

            self.assertEqual(found, newer)

    def test_find_latest_source_bundle_ignores_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name)
            (directory / workflow.SOURCE_BUNDLE_NAME).write_bytes(b"")

            self.assertIsNone(workflow.find_latest_source_bundle([directory]))

    def test_source_bundle_signature_detects_replaced_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / workflow.SOURCE_BUNDLE_NAME
            path.write_text("old", encoding="utf-8")
            old_signature = workflow.source_bundle_signature(path)

            path.write_text("new and larger", encoding="utf-8")
            new_signature = workflow.source_bundle_signature(path)

            self.assertIsNotNone(old_signature)
            self.assertIsNotNone(new_signature)
            self.assertNotEqual(old_signature, new_signature)

    def test_source_bundle_signature_accepts_missing_bundle(self) -> None:
        self.assertIsNone(workflow.source_bundle_signature(None))

    def test_read_collector_source_returns_exact_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "collector.js"
            source = "console.log('collector');\n"
            path.write_text(source, encoding="utf-8")

            self.assertEqual(workflow.read_collector_source(path), source)

    def test_read_collector_source_rejects_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "collector.js"
            path.write_text("   \n", encoding="utf-8")

            with self.assertRaises(ValueError):
                workflow.read_collector_source(path)

    def test_build_archive_command_is_unbuffered_and_uses_current_python(self) -> None:
        command = workflow.build_archive_command()

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "-u")
        self.assertEqual(Path(command[2]).name, "archive_chats.py")

    def test_windows_download_directories_are_unique(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "USERPROFILE": r"C:\Users\Example",
                "HOMEDRIVE": "C:",
                "HOMEPATH": r"\Users\Example",
            },
            clear=False,
        ):
            directories = workflow.windows_download_directories()

        normalized = [os.path.normcase(os.path.abspath(str(path))) for path in directories]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_create_archive_log_path_is_timestamped_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            reports = Path(temp_name) / "reports"
            when = datetime(2026, 8, 23, 11, 52, 14)

            first = workflow.create_archive_log_path(reports, when=when)
            self.assertEqual(first.name, "archive-workflow-2026-08-23_11-52-14.log")
            first.write_text("first", encoding="utf-8")

            second = workflow.create_archive_log_path(reports, when=when)
            self.assertEqual(second.name, "archive-workflow-2026-08-23_11-52-14-2.log")

    def test_latest_archive_log_path_uses_stable_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            reports = Path(temp_name) / "reports"
            path = workflow.latest_archive_log_path(reports)

            self.assertEqual(path, reports / "archive-workflow-latest.log")

    def test_auto_close_requires_archive_and_refresh_success(self) -> None:
        self.assertTrue(workflow.should_auto_close_archive(0, True))
        self.assertFalse(workflow.should_auto_close_archive(0, False))
        self.assertFalse(workflow.should_auto_close_archive(1, True))


if __name__ == "__main__":
    unittest.main()
