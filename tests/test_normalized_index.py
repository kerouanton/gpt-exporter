import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gpt_exporter.index.normalized import index_normalized_conversation
from gpt_exporter.model import Conversation, ContentBlock, Message
from gpt_exporter.index import _legacy_indexer as legacy


class NormalizedIndexTests(unittest.TestCase):
    def test_index_writes_common_conversation_messages_and_provider(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-1",
            title="Synthetic",
            created_at=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
            messages=(
                Message(
                    message_id="m1",
                    author_role="user",
                    created_at=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
                    text="hello exporter core",
                    content=(ContentBlock(kind="text", text="hello exporter core"),),
                ),
            ),
        )

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            database = root / "conversations-index.sqlite"
            source = root / "source.json"
            source.write_text("{}", encoding="utf-8")
            connection = legacy.connect_database(database)
            try:
                index_normalized_conversation(
                    connection,
                    conversation,
                    source_path=source,
                    archive_root=root,
                    source_mtime_ns=123,
                )

                row = connection.execute(
                    "SELECT title, source_mtime_ns FROM conversations WHERE conversation_id = ?",
                    ("conv-1",),
                ).fetchone()
                self.assertEqual(row["title"], "Synthetic")
                self.assertEqual(row["source_mtime_ns"], 123)

                provider = connection.execute(
                    "SELECT provider_key FROM conversation_providers WHERE conversation_id = ?",
                    ("conv-1",),
                ).fetchone()
                self.assertEqual(provider["provider_key"], "synthetic")

                message = connection.execute(
                    "SELECT author_role, body FROM messages WHERE conversation_id = ?",
                    ("conv-1",),
                ).fetchone()
                self.assertEqual(message["author_role"], "user")
                self.assertEqual(message["body"], "hello exporter core")

                fts = connection.execute(
                    "SELECT conversation_id FROM messages_fts WHERE messages_fts MATCH ?",
                    ('"exporter"',),
                ).fetchone()
                self.assertEqual(fts["conversation_id"], "conv-1")
            finally:
                connection.close()

    def test_reindex_preserves_project_assignments(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-1",
            title="Before",
        )

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            database = root / "conversations-index.sqlite"
            source = root / "source.json"
            source.write_text("{}", encoding="utf-8")
            connection = legacy.connect_database(database)
            try:
                index_normalized_conversation(
                    connection,
                    conversation,
                    source_path=source,
                    archive_root=root,
                )
                project_id = connection.execute(
                    "INSERT INTO work_projects (name, description, created_at) VALUES ('Keep', NULL, 'now')"
                ).lastrowid
                connection.execute(
                    "INSERT INTO conversation_work_projects (conversation_id, project_id, assigned_at) VALUES (?, ?, 'now')",
                    ("conv-1", project_id),
                )
                connection.commit()

                updated = Conversation(
                    provider_key="synthetic",
                    conversation_id="conv-1",
                    title="After",
                )
                index_normalized_conversation(
                    connection,
                    updated,
                    source_path=source,
                    archive_root=root,
                )

                count = connection.execute(
                    "SELECT COUNT(*) AS n FROM conversation_work_projects WHERE conversation_id = ?",
                    ("conv-1",),
                ).fetchone()["n"]
                self.assertEqual(count, 1)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
