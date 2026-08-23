import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import contextlib
import io
import json
import lzma
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.archive.importer import import_bundle


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONVERSATION_ID = "conv-import-library-001"


class ImportBundleLibraryTests(unittest.TestCase):
    def _conversation(self, answer: str) -> dict:
        return {
            "title": "Synthetic import library",
            "conversation_id": CONVERSATION_ID,
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
                        "content": {"content_type": "text", "parts": ["Question"]},
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
                        "content": {"content_type": "text", "parts": [answer]},
                        "metadata": {},
                    },
                },
            },
        }

    def _write_bundle(self, path: Path, answer: str) -> None:
        payload = {
            "format": "chatgpt-archive-source-v1",
            "conversations": [self._conversation(answer)],
            "assets": [],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary
            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.archive.importer"],
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

    def test_library_call_is_quiet_without_progress_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            bundle = Path(temporary) / "bundle.json"
            self._write_bundle(bundle, "Answer")

            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                result = import_bundle(bundle, archive_root=root)

            self.assertTrue(result.success)
            self.assertEqual(captured.getvalue(), "")
            self.assertEqual(result.written_conversations, 1)

    def test_incremental_import_preserves_shorter_snapshot_and_batch_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            bundle = Path(temporary) / "bundle.json"

            self._write_bundle(bundle, "A much longer synthetic answer for the first snapshot")
            first = import_bundle(bundle, archive_root=root)
            self.assertTrue(first.success)
            self.assertEqual(len(first.current_batch), 1)

            archived = next((root / "downloads").glob(f"*_{CONVERSATION_ID}.json.xz"))
            with lzma.open(archived, "rb") as handle:
                original = handle.read()

            self._write_bundle(bundle, "Short")
            second = import_bundle(bundle, archive_root=root)
            self.assertTrue(second.success)
            self.assertEqual(second.current_batch, ())

            with lzma.open(archived, "rb") as handle:
                self.assertEqual(handle.read(), original)

            batch = json.loads(
                (root / "reports" / "current-batch.json").read_text(encoding="utf-8")
            )
            self.assertEqual(batch["conversation_files"], [])

    def test_invalid_bundle_fails_before_creating_archive_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            bundle = Path(temporary) / "bundle.json"
            bundle.write_text('{"format":"wrong"}', encoding="utf-8")

            with self.assertRaises(ValueError):
                import_bundle(bundle, archive_root=root)

            self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
