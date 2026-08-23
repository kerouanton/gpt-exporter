import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import archive_chats


class V28PipelineCharacterizationTests(unittest.TestCase):
    def run_pipeline(
        self,
        archive_root: Path,
        *,
        step_side_effect=None,
        batch_files: list[str] | None = None,
    ) -> tuple[int, mock.Mock, mock.Mock, mock.Mock, list[str]]:
        downloads = archive_root / "downloads"
        assets = archive_root / "assets"
        reports = archive_root / "reports"
        downloads.mkdir(parents=True)
        assets.mkdir(parents=True)
        reports.mkdir(parents=True)
        (downloads / "conversation.json.xz").write_bytes(b"placeholder")

        if batch_files is not None:
            (reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": batch_files}),
                encoding="utf-8",
            )

        source_bundle = archive_root / "chatgpt-archive-source.json"
        source_bundle.write_text("{}", encoding="utf-8")

        events: list[str] = []

        def record_step(label: str, script: str, arguments=None) -> None:
            events.append(script)
            if step_side_effect is not None:
                step_side_effect(label, script, arguments)

        def record_index() -> None:
            events.append("index-library")

        run_step = mock.Mock(side_effect=record_step)
        run_index_step = mock.Mock(side_effect=record_index)
        delete_bundle = mock.Mock()

        with (
            mock.patch.object(archive_chats, "ARCHIVE_ROOT", archive_root),
            mock.patch.object(archive_chats, "DOWNLOADS_DIR", downloads),
            mock.patch.object(archive_chats, "ASSETS_DIR", assets),
            mock.patch.object(archive_chats, "REPORTS_DIR", reports),
            mock.patch.object(
                archive_chats,
                "GENERATED_DIRECTORIES",
                (downloads, assets, reports),
            ),
            mock.patch.object(archive_chats, "migrate_legacy_archive"),
            mock.patch.object(archive_chats, "migrate_output_layout"),
            mock.patch.object(archive_chats, "migrate_json_storage"),
            mock.patch.object(
                archive_chats,
                "require_source_bundle",
                return_value=source_bundle,
            ),
            mock.patch.object(
                archive_chats,
                "delete_consumed_source_bundle",
                delete_bundle,
            ),
            mock.patch.object(archive_chats, "run_step", run_step),
            mock.patch.object(archive_chats, "run_index_step", run_index_step),
            mock.patch.object(sys, "argv", ["archive_chats.py"]),
        ):
            result = archive_chats.main()

        return result, run_step, run_index_step, delete_bundle, events

    def test_pipeline_step_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, run_step, run_index_step, delete_bundle, events = self.run_pipeline(
                Path(temporary_directory),
                batch_files=["conversation.json.xz"],
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            [
                "import_browser_bundle.py",
                "inventory_media.py",
                "build_asset_manifest.py",
                "export_all.py",
                "index-library",
            ],
        )
        run_index_step.assert_called_once_with()
        delete_bundle.assert_called_once()

    def test_source_bundle_is_not_deleted_when_a_step_fails(self) -> None:
        def fail_inventory(label: str, script: str, arguments=None) -> None:
            if script == "inventory_media.py":
                raise RuntimeError("synthetic inventory failure")

        with tempfile.TemporaryDirectory() as temporary_directory:
            result, run_step, run_index_step, delete_bundle, events = self.run_pipeline(
                Path(temporary_directory),
                step_side_effect=fail_inventory,
                batch_files=["conversation.json.xz"],
            )

        self.assertEqual(result, 1)
        self.assertEqual(
            events,
            ["import_browser_bundle.py", "inventory_media.py"],
        )
        run_index_step.assert_not_called()
        delete_bundle.assert_not_called()

    def test_empty_current_batch_skips_export_but_still_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result, run_step, run_index_step, delete_bundle, events = self.run_pipeline(
                Path(temporary_directory),
                batch_files=[],
            )

        self.assertEqual(result, 0)
        self.assertEqual(
            events,
            [
                "import_browser_bundle.py",
                "inventory_media.py",
                "build_asset_manifest.py",
                "index-library",
            ],
        )
        self.assertNotIn("export_all.py", events)
        run_index_step.assert_called_once_with()
        delete_bundle.assert_called_once()


if __name__ == "__main__":
    unittest.main()
