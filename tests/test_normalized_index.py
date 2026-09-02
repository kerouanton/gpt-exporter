import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from gpt_exporter.index.normalized import index_normalized_conversation
from gpt_exporter.model import Conversation, ConversationOrigin, ContentBlock, Message
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

    def test_index_writes_normalized_origins_and_native_index_metadata(self) -> None:
        conversation = Conversation(
            provider_key="chatgpt",
            conversation_id="conv-origin",
            title="Origin",
            origins=(
                ConversationOrigin(
                    origin_id="g-p-project",
                    origin_type="project",
                    source="message.metadata.gizmo_id",
                ),
                ConversationOrigin(
                    origin_id="g-custom",
                    origin_type="custom_gpt",
                    source="top_level.gizmo_id",
                ),
            ),
            index_metadata={
                "gizmo_id": "g-custom",
                "gizmo_type": "custom",
                "conversation_template_id": "g-p-project",
                "conversation_origin": "native-origin",
                "default_model_slug": "gpt-test",
            },
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
                row = connection.execute(
                    """
                    SELECT primary_origin_type, primary_origin_id, gizmo_id, gizmo_type,
                           conversation_template_id, conversation_origin, default_model_slug
                    FROM conversations WHERE conversation_id = ?
                    """,
                    ("conv-origin",),
                ).fetchone()
                origins = connection.execute(
                    """
                    SELECT co.origin_id, o.origin_type, co.source, co.is_primary
                    FROM conversation_origins AS co
                    JOIN origins AS o ON o.origin_id = co.origin_id
                    WHERE co.conversation_id = ?
                    ORDER BY co.origin_id
                    """,
                    ("conv-origin",),
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(row["primary_origin_type"], "project")
        self.assertEqual(row["primary_origin_id"], "g-p-project")
        self.assertEqual(row["gizmo_id"], "g-custom")
        self.assertEqual(row["gizmo_type"], "custom")
        self.assertEqual(row["conversation_template_id"], "g-p-project")
        self.assertEqual(row["conversation_origin"], "native-origin")
        self.assertEqual(row["default_model_slug"], "gpt-test")
        self.assertEqual(
            [(item["origin_id"], item["origin_type"], item["source"], item["is_primary"]) for item in origins],
            [
                ("g-custom", "custom_gpt", "top_level.gizmo_id", 0),
                ("g-p-project", "project", "message.metadata.gizmo_id", 1),
            ],
        )

    def test_index_uses_search_projection_not_display_projection(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-projection",
            title="Projection",
            messages=(
                Message(
                    message_id="visible-only",
                    author_role="assistant",
                    text="Rendered attachment details",
                    is_visible=True,
                    is_indexable=False,
                    display_order=1,
                ),
                Message(
                    message_id="both",
                    author_role="user",
                    text="Rendered user text",
                    search_text="Indexed user text",
                    is_visible=True,
                    is_indexable=True,
                    display_order=2,
                    search_order=2,
                    content=(ContentBlock(kind="text", text="Rendered user text"),),
                ),
                Message(
                    message_id="search-only",
                    author_role="assistant",
                    text="Search fallback",
                    search_text="Alternative branch text",
                    is_visible=False,
                    is_indexable=True,
                    search_order=1,
                    content=(ContentBlock(kind="text", text="Alternative branch text"),),
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
                )
                rows = connection.execute(
                    """
                    SELECT message_id, message_order, body
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY message_order
                    """,
                    ("conv-projection",),
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(
            [(row["message_id"], row["message_order"], row["body"]) for row in rows],
            [
                ("search-only", 1, "Alternative branch text"),
                ("both", 2, "Indexed user text"),
            ],
        )

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
