from __future__ import annotations

import json
import lzma
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gpt_exporter.index.storage import SCHEMA_VERSION, connect_database, upsert_provider_metadata


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_GPT_COLUMNS = {
    "gizmo_id",
    "gizmo_type",
    "conversation_template_id",
    "conversation_origin",
    "default_model_slug",
}


class ProviderMetadataSchemaV6Tests(unittest.TestCase):
    def test_fresh_schema_contains_no_chatgpt_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "fresh.sqlite"
            with closing(connect_database(database)) as connection:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(conversations)")
                }
                message_columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(messages)")
                }
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }

            self.assertEqual(version, 6)
            self.assertEqual(SCHEMA_VERSION, 6)
            self.assertTrue(FORBIDDEN_GPT_COLUMNS.isdisjoint(columns))
            self.assertIn("author_name", message_columns)
            self.assertIn("conversation_provider_metadata", tables)

    def test_v4_migration_preserves_provider_metadata_and_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "legacy-v4.sqlite"
            connection = sqlite3.connect(database)
            try:
                connection.executescript(
                    """
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE conversations (
                        conversation_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT,
                        updated_at TEXT,
                        source_json_path TEXT NOT NULL,
                        source_mtime_ns INTEGER NOT NULL,
                        docx_path TEXT,
                        indexed_at TEXT NOT NULL,
                        primary_origin_type TEXT NOT NULL DEFAULT 'standard',
                        primary_origin_id TEXT,
                        gizmo_id TEXT,
                        gizmo_type TEXT,
                        conversation_template_id TEXT,
                        conversation_origin TEXT,
                        default_model_slug TEXT
                    );
                    CREATE TABLE messages (
                        id INTEGER PRIMARY KEY,
                        conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                            ON DELETE CASCADE,
                        message_id TEXT NOT NULL,
                        message_order INTEGER NOT NULL,
                        author_role TEXT NOT NULL,
                        created_at TEXT,
                        content_type TEXT,
                        body TEXT NOT NULL
                    );
                    PRAGMA user_version = 4;
                    """
                )
                connection.execute(
                    """
                    INSERT INTO conversations (
                        conversation_id, title, source_json_path, source_mtime_ns,
                        indexed_at, primary_origin_type, primary_origin_id,
                        gizmo_id, gizmo_type, conversation_template_id,
                        conversation_origin, default_model_slug
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "conv-v4",
                        "Migrated conversation",
                        "downloads/conv-v4.json.xz",
                        123,
                        "2026-09-07T10:00:00+00:00",
                        "custom_gpt",
                        "g-example",
                        "g-example",
                        "custom_gpt",
                        "template-1",
                        "chatgpt",
                        "gpt-5.6",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, message_id, message_order,
                        author_role, content_type, body
                    ) VALUES ('conv-v4', 'm1', 1, 'user', 'text', 'hello')
                    """
                )
                connection.commit()
            finally:
                connection.close()

            with closing(connect_database(database)) as migrated:
                version = migrated.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row["name"]
                    for row in migrated.execute("PRAGMA table_info(conversations)")
                }
                message_columns = {
                    row["name"]
                    for row in migrated.execute("PRAGMA table_info(messages)")
                }
                metadata_row = migrated.execute(
                    """
                    SELECT provider_id, metadata_json
                    FROM conversation_provider_metadata
                    WHERE conversation_id = 'conv-v4'
                    """
                ).fetchone()
                message_count = migrated.execute(
                    "SELECT COUNT(*) FROM messages WHERE conversation_id = 'conv-v4'"
                ).fetchone()[0]
                fk_errors = migrated.execute("PRAGMA foreign_key_check").fetchall()

            self.assertEqual(version, 6)
            self.assertTrue(FORBIDDEN_GPT_COLUMNS.isdisjoint(columns))
            self.assertIn("author_name", message_columns)
            self.assertEqual(message_count, 1)
            self.assertEqual(fk_errors, [])
            self.assertIsNotNone(metadata_row)
            self.assertEqual(metadata_row["provider_id"], "gpt")
            metadata = json.loads(metadata_row["metadata_json"])
            self.assertEqual(metadata["gizmo_id"], "g-example")
            self.assertEqual(metadata["gizmo_type"], "custom_gpt")
            self.assertEqual(metadata["conversation_template_id"], "template-1")
            self.assertEqual(metadata["conversation_origin"], "chatgpt")
            self.assertEqual(metadata["default_model_slug"], "gpt-5.6")

    def test_provider_metadata_table_accepts_non_gpt_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "discord.sqlite"
            with closing(connect_database(database)) as connection:
                connection.execute(
                    """
                    INSERT INTO conversations (
                        conversation_id, title, source_json_path, source_mtime_ns,
                        indexed_at, primary_origin_type, primary_origin_id
                    ) VALUES ('discord-1', 'Discord thread', 'thread.json', 1,
                              '2026-09-07T10:00:00+00:00', 'standard', NULL)
                    """
                )
                upsert_provider_metadata(
                    connection,
                    "discord-1",
                    "discord",
                    {"guild_id": "guild-1", "channel_id": "channel-2"},
                )
                row = connection.execute(
                    """
                    SELECT metadata_json FROM conversation_provider_metadata
                    WHERE conversation_id = 'discord-1' AND provider_id = 'discord'
                    """
                ).fetchone()

            self.assertEqual(
                json.loads(row["metadata_json"]),
                {"channel_id": "channel-2", "guild_id": "guild-1"},
            )

    def test_root_chatgpt_index_cli_creates_schema_v6(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            downloads = archive_root / "downloads"
            downloads.mkdir(parents=True)
            database = archive_root / "conversations-index.sqlite"
            source = downloads / "conversation.json.xz"
            conversation = {
                "conversation_id": "cli-v6",
                "title": "CLI v6",
                "create_time": 1_700_000_000.0,
                "update_time": 1_700_000_100.0,
                "gizmo_id": "g-cli",
                "gizmo_type": "custom_gpt",
                "default_model_slug": "gpt-5.6",
                "mapping": {
                    "u": {
                        "message": {
                            "id": "m-u",
                            "author": {"role": "user"},
                            "create_time": 1_700_000_010.0,
                            "content": {"content_type": "text", "parts": ["hello"]},
                            "metadata": {},
                        }
                    }
                },
            }
            with lzma.open(source, "wt", encoding="utf-8") as handle:
                json.dump(conversation, handle)

            completed = subprocess.run(
                [
                    sys.executable,
                    "index_chatgpt_archive.py",
                    "--archive-root",
                    str(archive_root),
                    "--downloads-dir",
                    str(downloads),
                    "--database",
                    str(database),
                    "index",
                ],
                cwd=REPOSITORY_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            with closing(sqlite3.connect(database)) as connection:
                connection.row_factory = sqlite3.Row
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row["name"]
                    for row in connection.execute("PRAGMA table_info(conversations)")
                }
                metadata_row = connection.execute(
                    """
                    SELECT metadata_json FROM conversation_provider_metadata
                    WHERE conversation_id = 'cli-v6' AND provider_id = 'gpt'
                    """
                ).fetchone()

            self.assertEqual(version, 6)
            self.assertTrue(FORBIDDEN_GPT_COLUMNS.isdisjoint(columns))
            self.assertIsNotNone(metadata_row)
            metadata = json.loads(metadata_row["metadata_json"])
            self.assertEqual(metadata["gizmo_id"], "g-cli")
            self.assertEqual(metadata["default_model_slug"], "gpt-5.6")


if __name__ == "__main__":
    unittest.main()
