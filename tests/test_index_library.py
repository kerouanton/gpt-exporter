import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.index import update_index


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class IndexLibraryTests(unittest.TestCase):
    def _write_conversation(
        self,
        archive_root: Path,
        *,
        filename: str = "conversation.json.xz",
        conversation_id: str = "conv-index-library-001",
        answer: str = "Synthetic indexed answer",
    ) -> Path:
        downloads = archive_root / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        conversation = {
            "title": "Synthetic index library",
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
                        "content": {
                            "content_type": "text",
                            "parts": ["Synthetic indexed question"],
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
                        "content": {
                            "content_type": "text",
                            "parts": [answer],
                        },
                        "metadata": {},
                    },
                },
            },
        }
        path = downloads / filename
        with lzma.open(path, "wt", encoding="utf-8", preset=6) as handle:
            json.dump(conversation, handle, ensure_ascii=False)
        return path

    def test_incremental_update_returns_structured_counts_and_closes_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(archive_root)
            database_path = archive_root / "conversations-index.sqlite"

            first = update_index(archive_root)
            second = update_index(archive_root)

            self.assertEqual(first.total_files, 1)
            self.assertEqual(first.updated, 1)
            self.assertEqual(first.unchanged_or_skipped, 0)
            self.assertEqual(first.failed, 0)
            self.assertTrue(first.success)
            self.assertEqual(second.updated, 0)
            self.assertEqual(second.unchanged_or_skipped, 1)
            self.assertEqual(second.failed, 0)

            moved = database_path.with_name("moved.sqlite")
            database_path.replace(moved)
            moved.replace(database_path)
            self.assertTrue(database_path.is_file())

    def test_incremental_update_preserves_project_category_and_tag_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            source = self._write_conversation(archive_root)
            database_path = archive_root / "conversations-index.sqlite"
            update_index(archive_root)

            with sqlite3.connect(database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    "INSERT INTO categories(name, description, created_at) VALUES (?, NULL, ?)",
                    ("Category A", "2026-01-01T00:00:00+00:00"),
                )
                connection.execute(
                    "INSERT INTO tags(name, description, created_at) VALUES (?, NULL, ?)",
                    ("Tag A", "2026-01-01T00:00:00+00:00"),
                )
                connection.execute(
                    "INSERT INTO work_projects(name, description, created_at) VALUES (?, NULL, ?)",
                    ("Project A", "2026-01-01T00:00:00+00:00"),
                )
                connection.execute(
                    "INSERT INTO conversation_categories(conversation_id, category_id, assigned_at) "
                    "SELECT ?, category_id, ? FROM categories WHERE name = ?",
                    (
                        "conv-index-library-001",
                        "2026-01-01T00:00:00+00:00",
                        "Category A",
                    ),
                )
                connection.execute(
                    "INSERT INTO conversation_tags(conversation_id, tag_id, assigned_at) "
                    "SELECT ?, tag_id, ? FROM tags WHERE name = ?",
                    (
                        "conv-index-library-001",
                        "2026-01-01T00:00:00+00:00",
                        "Tag A",
                    ),
                )
                connection.execute(
                    "INSERT INTO conversation_work_projects(conversation_id, project_id, assigned_at) "
                    "SELECT ?, project_id, ? FROM work_projects WHERE name = ?",
                    (
                        "conv-index-library-001",
                        "2026-01-01T00:00:00+00:00",
                        "Project A",
                    ),
                )
                connection.commit()

            current = source.stat().st_mtime_ns
            os.utime(source, ns=(current + 2_000_000_000, current + 2_000_000_000))
            result = update_index(archive_root)
            self.assertEqual(result.updated, 1)

            with sqlite3.connect(database_path) as connection:
                category_count = connection.execute(
                    "SELECT COUNT(*) FROM conversation_categories WHERE conversation_id = ?",
                    ("conv-index-library-001",),
                ).fetchone()[0]
                tag_count = connection.execute(
                    "SELECT COUNT(*) FROM conversation_tags WHERE conversation_id = ?",
                    ("conv-index-library-001",),
                ).fetchone()[0]
                project_count = connection.execute(
                    "SELECT COUNT(*) FROM conversation_work_projects WHERE conversation_id = ?",
                    ("conv-index-library-001",),
                ).fetchone()[0]

            self.assertEqual(category_count, 1)
            self.assertEqual(tag_count, 1)
            self.assertEqual(project_count, 1)

    def test_bad_source_is_reported_without_stopping_other_conversations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            self._write_conversation(
                archive_root,
                filename="b-valid.json.xz",
                conversation_id="conv-valid",
            )
            corrupt = archive_root / "downloads" / "a-corrupt.json.xz"
            corrupt.write_bytes(b"not an xz stream")

            result = update_index(archive_root)

            self.assertEqual(result.total_files, 2)
            self.assertEqual(result.updated, 1)
            self.assertEqual(result.failed, 1)
            self.assertFalse(result.success)
            self.assertEqual(result.failures[0].source_path, corrupt.resolve())

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary

            completed = subprocess.run(
                [sys.executable, "-c", "import gpt_exporter.index"],
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
