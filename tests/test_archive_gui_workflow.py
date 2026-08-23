import os
import queue
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

    def test_archive_worker_calls_pipeline_in_process_and_queues_progress(self) -> None:
        events: queue.Queue[tuple[str, object]] = queue.Queue()
        archive_root = Path("C:/synthetic/archive")
        source_bundle = Path("C:/synthetic/Downloads/chatgpt-archive-source.json")

        def fake_archive_bundle(**kwargs):
            kwargs["progress"]("synthetic progress")
            return mock.sentinel.pipeline_result

        with mock.patch.object(
            workflow,
            "archive_bundle",
            side_effect=fake_archive_bundle,
        ) as archive_bundle:
            workflow.run_archive_pipeline_worker(
                events,
                archive_root=archive_root,
                source_bundle=source_bundle,
            )

        archive_bundle.assert_called_once()
        _, kwargs = archive_bundle.call_args
        self.assertEqual(kwargs["archive_root"], archive_root)
        self.assertEqual(kwargs["source_bundle"], source_bundle)
        self.assertEqual(kwargs["legacy_root"], workflow.ROOT)
        self.assertTrue(callable(kwargs["progress"]))
        self.assertEqual(events.get_nowait(), ("line", "synthetic progress\n"))
        self.assertEqual(events.get_nowait(), ("done", 0))
        self.assertTrue(events.empty())

    def test_archive_worker_reports_pipeline_failure_without_touching_tk(self) -> None:
        events: queue.Queue[tuple[str, object]] = queue.Queue()

        with mock.patch.object(
            workflow,
            "archive_bundle",
            side_effect=RuntimeError("synthetic pipeline failure"),
        ):
            workflow.run_archive_pipeline_worker(
                events,
                archive_root=Path("C:/synthetic/archive"),
                source_bundle=Path("C:/synthetic/bundle.json"),
            )

        kind, message = events.get_nowait()
        self.assertEqual(kind, "line")
        self.assertIn("ERROR: synthetic pipeline failure", str(message))
        self.assertEqual(events.get_nowait(), ("done", 1))
        self.assertTrue(events.empty())

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
