import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import archive_browser
import archive_chats


class IndexSyncWorkflowTests(unittest.TestCase):
    def test_archive_workflow_updates_index_after_export(self) -> None:
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
                mock.patch.object(sys, "argv", ["archive_chats.py"]),
            ):
                result = archive_chats.main()

            self.assertEqual(result, 0)
            index_calls = [
                call
                for call in run_step.call_args_list
                if call.args[1] == "index_chatgpt_archive.py"
            ]
            self.assertEqual(len(index_calls), 1)

            label, script, arguments = index_calls[0].args
            self.assertEqual(label, "5/5 - Update archive search index")
            self.assertEqual(script, "index_chatgpt_archive.py")
            self.assertEqual(arguments[-1], "index")
            self.assertEqual(
                arguments[arguments.index("--database") + 1],
                str(archive_root / "conversations-index.sqlite"),
            )

    def test_browser_index_command_uses_open_database_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            database_path = archive_root / "conversations-index.sqlite"

            command = archive_browser.build_index_command(database_path)

            self.assertEqual(command[0], sys.executable)
            self.assertEqual(Path(command[1]).name, "index_chatgpt_archive.py")
            self.assertEqual(command[-1], "index")
            self.assertEqual(
                command[command.index("--archive-root") + 1],
                str(archive_root),
            )
            self.assertEqual(
                command[command.index("--downloads-dir") + 1],
                str(archive_root / "downloads"),
            )
            self.assertEqual(
                command[command.index("--database") + 1],
                str(database_path),
            )


if __name__ == "__main__":
    unittest.main()
