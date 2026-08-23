import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import archive_chats
import gpt_exporter_gui as gui


class IndexSyncWorkflowTests(unittest.TestCase):
    def test_archive_workflow_updates_index_after_export_in_process(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            downloads_dir = archive_root / "downloads"
            assets_dir = archive_root / "assets"
            reports_dir = archive_root / "reports"
            downloads_dir.mkdir()
            assets_dir.mkdir()
            reports_dir.mkdir()
            (downloads_dir / "conversation.json.xz").write_bytes(b"placeholder")
            source_bundle = archive_root / "chatgpt-archive-source.json"

            with (
                mock.patch.object(archive_chats, "ARCHIVE_ROOT", archive_root),
                mock.patch.object(archive_chats, "DOWNLOADS_DIR", downloads_dir),
                mock.patch.object(archive_chats, "ASSETS_DIR", assets_dir),
                mock.patch.object(archive_chats, "REPORTS_DIR", reports_dir),
                mock.patch.object(
                    archive_chats,
                    "GENERATED_DIRECTORIES",
                    (downloads_dir, assets_dir, reports_dir),
                ),
                mock.patch.object(archive_chats, "migrate_legacy_archive"),
                mock.patch.object(archive_chats, "migrate_output_layout"),
                mock.patch.object(archive_chats, "migrate_json_storage"),
                mock.patch.object(
                    archive_chats,
                    "require_source_bundle",
                    return_value=source_bundle,
                ),
                mock.patch.object(archive_chats, "delete_consumed_source_bundle"),
                mock.patch.object(archive_chats, "run_step") as run_step,
                mock.patch.object(archive_chats, "run_index_step") as run_index_step,
                mock.patch.object(sys, "argv", ["archive_chats.py"]),
            ):
                result = archive_chats.main()

            self.assertEqual(result, 0)
            run_index_step.assert_called_once_with()
            self.assertNotIn(
                "index_chatgpt_archive.py",
                [call.args[1] for call in run_step.call_args_list],
            )

    def test_archive_index_step_uses_explicit_archive_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            downloads_dir = archive_root / "downloads"
            database_path = archive_root / "conversations-index.sqlite"

            with (
                mock.patch.object(archive_chats, "ARCHIVE_ROOT", archive_root),
                mock.patch.object(archive_chats, "DOWNLOADS_DIR", downloads_dir),
                mock.patch.object(
                    archive_chats,
                    "update_archive_index",
                    return_value=mock.sentinel.index_result,
                ) as update_index,
            ):
                result = archive_chats.run_index_step()

            self.assertIs(result, mock.sentinel.index_result)
            update_index.assert_called_once()
            args, kwargs = update_index.call_args
            self.assertEqual(args, (archive_root,))
            self.assertEqual(kwargs["downloads_dir"], downloads_dir)
            self.assertEqual(kwargs["database_path"], database_path)
            self.assertIs(kwargs["progress"], print)

    def test_gui_index_helper_uses_open_database_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            database_path = archive_root / "conversations-index.sqlite"

            with mock.patch.object(
                gui,
                "update_archive_index",
                return_value=mock.sentinel.index_result,
            ) as update_index:
                result = gui.update_browser_index(database_path)

            self.assertIs(result, mock.sentinel.index_result)
            update_index.assert_called_once_with(
                archive_root.resolve(),
                downloads_dir=(archive_root / "downloads").resolve(),
                database_path=database_path.resolve(),
                progress=None,
            )


if __name__ == "__main__":
    unittest.main()
