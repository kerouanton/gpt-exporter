from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpt_exporter.index.engine import update_index
from gpt_exporter.index.storage import connect_database, now_iso


class IndexFastPathTests(unittest.TestCase):
    def _archive_with_indexed_source(self) -> tuple[tempfile.TemporaryDirectory, Path, Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        downloads = root / "downloads"
        downloads.mkdir(parents=True)
        source = downloads / "conversation.json.xz"
        # The fast path must not need to open or decompress an unchanged source.
        source.write_bytes(b"not-an-xz-stream")
        database = root / "conversations-index.sqlite"

        connection = connect_database(database)
        try:
            connection.execute(
                """
                INSERT INTO conversations (
                    conversation_id, title, source_json_path,
                    source_mtime_ns, indexed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "conversation-1",
                    "Existing conversation",
                    str(source.resolve()),
                    source.stat().st_mtime_ns,
                    now_iso(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

        return temporary, root, downloads, database

    def test_unchanged_source_is_skipped_before_decompression(self) -> None:
        temporary, root, downloads, database = self._archive_with_indexed_source()
        self.addCleanup(temporary.cleanup)

        native_calls = 0

        def native_indexer(*_args, **_kwargs) -> bool:
            nonlocal native_calls
            native_calls += 1
            return True

        with patch(
            "gpt_exporter.index.engine.try_read_canonical_conversation",
            side_effect=AssertionError("unchanged source should not be parsed"),
        ):
            result = update_index(
                root,
                downloads_dir=downloads,
                database_path=database,
                native_indexer=native_indexer,
            )

        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.unchanged_or_skipped, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(native_calls, 0)

    def test_changed_mtime_falls_through_to_normal_indexing(self) -> None:
        temporary, root, downloads, database = self._archive_with_indexed_source()
        self.addCleanup(temporary.cleanup)
        source = downloads / "conversation.json.xz"
        original = source.stat().st_mtime_ns
        os.utime(source, ns=(original + 1_000_000_000, original + 1_000_000_000))

        native_calls = 0

        def native_indexer(*_args, **_kwargs) -> bool:
            nonlocal native_calls
            native_calls += 1
            return True

        with patch(
            "gpt_exporter.index.engine.try_read_canonical_conversation",
            return_value=None,
        ):
            result = update_index(
                root,
                downloads_dir=downloads,
                database_path=database,
                native_indexer=native_indexer,
            )

        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(native_calls, 1)

    def test_force_bypasses_fast_path(self) -> None:
        temporary, root, downloads, database = self._archive_with_indexed_source()
        self.addCleanup(temporary.cleanup)

        native_calls = 0

        def native_indexer(*_args, **_kwargs) -> bool:
            nonlocal native_calls
            native_calls += 1
            return True

        with patch(
            "gpt_exporter.index.engine.try_read_canonical_conversation",
            return_value=None,
        ):
            result = update_index(
                root,
                downloads_dir=downloads,
                database_path=database,
                native_indexer=native_indexer,
                force=True,
            )

        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(native_calls, 1)


if __name__ == "__main__":
    unittest.main()
