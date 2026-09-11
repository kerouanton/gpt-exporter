from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.core import CanonicalConversation
from gpt_exporter.core.serialization import write_canonical_conversation
from gpt_exporter.providers.discord.raw_archive import read_raw_bytes
from gpt_exporter.providers.discord.ui.remote_delete_actions import DiscordRemoteDeleteActions
from gpt_exporter.ui import workspace_shell
from gpt_exporter.workspaces import ConversationWorkspace


class DiscordWorkspaceBrowserTests(unittest.TestCase):
    def test_existing_discord_workspace_migrates_human_names_docx_and_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = ConversationWorkspace("Discord", "discord", root)
            old_docx = root / "Discord DM 123456.docx"
            old_docx.write_bytes(b"PK-existing-docx")
            old_raw = root / "raw" / "discord_dm_123456.json"
            old_raw.parent.mkdir()
            old_raw.write_text("{}", encoding="utf-8")
            old_canonical = root / "downloads" / "discord_dm_123456.json.xz"
            old_canonical.parent.mkdir()

            metadata = {
                "conversation_type": "dm",
                "current_user": {"id": "1", "username": "gadgetmcs", "display_name": "Gadget MCS"},
                "participants": [
                    {"id": "2", "name": "soundy", "is_self": False},
                    {"id": "1", "name": "Gadget MCS", "is_self": True},
                ],
            }
            write_canonical_conversation(
                old_canonical,
                CanonicalConversation(
                    conversation_id="discord:123456",
                    provider_id="discord",
                    title="(117) Discord | @soundy",
                    messages=(),
                    metadata=metadata,
                ),
            )

            with closing(sqlite3.connect(workspace.database_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE conversations (
                        conversation_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        source_json_path TEXT NOT NULL,
                        docx_path TEXT,
                        primary_origin_type TEXT NOT NULL,
                        primary_origin_id TEXT
                    );
                    CREATE TABLE conversation_provider_metadata (
                        conversation_id TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    CREATE TABLE canonical_conversation_sources (
                        conversation_id TEXT PRIMARY KEY,
                        source_path TEXT NOT NULL
                    );
                    CREATE TABLE categories (
                        category_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                        description TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE conversation_categories (
                        conversation_id TEXT NOT NULL,
                        category_id INTEGER NOT NULL,
                        assigned_at TEXT NOT NULL,
                        PRIMARY KEY (conversation_id, category_id)
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO conversations VALUES (?, ?, ?, NULL, 'standard', NULL)",
                    ("discord:123456", "(117) Discord | @soundy", str(old_canonical)),
                )
                connection.execute(
                    "INSERT INTO conversation_provider_metadata VALUES (?, 'discord', ?)",
                    ("discord:123456", json.dumps(metadata)),
                )
                connection.execute(
                    "INSERT INTO canonical_conversation_sources VALUES (?, ?)",
                    ("discord:123456", str(old_canonical)),
                )
                connection.commit()

            actions = DiscordRemoteDeleteActions(SimpleNamespace(), workspace)
            self.assertTrue(actions.prepare_index())

            stem = "Discord DM Gadget MCS ↔ soundy 123456"
            new_docx = root / f"{stem}.docx"
            new_raw = root / "downloads" / f"{stem}.raw.json.xz"
            new_canonical = root / "downloads" / f"{stem}.canonical.json.xz"
            self.assertTrue(new_docx.is_file())
            self.assertTrue(new_raw.is_file())
            self.assertEqual(read_raw_bytes(new_raw), b"{}")
            self.assertTrue(new_canonical.is_file())
            self.assertFalse(old_docx.exists())
            self.assertFalse(old_raw.exists())

            with closing(sqlite3.connect(workspace.database_path)) as connection:
                row = connection.execute(
                    "SELECT title, source_json_path, docx_path, primary_origin_type, primary_origin_id FROM conversations"
                ).fetchone()
                canonical_source = connection.execute(
                    "SELECT source_path FROM canonical_conversation_sources"
                ).fetchone()[0]
                category = connection.execute(
                    """
                    SELECT cat.name
                    FROM conversation_categories cc
                    JOIN categories cat ON cat.category_id = cc.category_id
                    WHERE cc.conversation_id = 'discord:123456'
                    """
                ).fetchone()[0]
            self.assertEqual(row[0], "Gadget MCS ↔ soundy")
            self.assertEqual(row[1], str(new_canonical))
            self.assertEqual(row[2], str(new_docx))
            self.assertEqual(row[3], "Direct Messages")
            self.assertEqual(row[4], "123456")
            self.assertEqual(canonical_source, str(new_canonical))
            self.assertEqual(category, "Discord Direct Message")
            self.assertEqual(
                actions.resolve_docx_path({"conversation_id": "discord:123456"}),
                new_docx,
            )

    def test_switch_workspace_menu_reuses_active_tk_parent_and_switches_selection(self) -> None:
        fake = SimpleNamespace(
            workspace=SimpleNamespace(name="ChatGPT"),
            _enabled_workspaces=mock.Mock(return_value=("ChatGPT", "Discord")),
            switch_workspace=mock.Mock(),
        )
        with mock.patch.object(workspace_shell, "choose_workspace", return_value="Discord") as chooser:
            workspace_shell.ConversationWorkspaceApp.switch_workspace_dialog(fake)

        chooser.assert_called_once_with(
            ("ChatGPT", "Discord"),
            default_workspace_name="ChatGPT",
            parent=fake,
        )
        fake.switch_workspace.assert_called_once_with("Discord")


if __name__ == "__main__":
    unittest.main()
