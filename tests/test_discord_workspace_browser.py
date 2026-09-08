from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.providers.discord.ui.workspace_actions import DiscordWorkspaceActions
from gpt_exporter.ui import workspace_shell
from gpt_exporter.workspaces import ConversationWorkspace


class DiscordWorkspaceBrowserTests(unittest.TestCase):
    def test_existing_discord_workspace_repairs_docx_path_and_dm_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = ConversationWorkspace("Discord", "discord", root)
            docx_path = root / "Discord DM 123456.docx"
            docx_path.write_bytes(b"PK-existing-docx")

            with closing(sqlite3.connect(workspace.database_path)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE conversations (
                        conversation_id TEXT PRIMARY KEY,
                        docx_path TEXT,
                        primary_origin_type TEXT NOT NULL,
                        primary_origin_id TEXT
                    );
                    CREATE TABLE conversation_provider_metadata (
                        conversation_id TEXT NOT NULL,
                        provider_id TEXT NOT NULL,
                        metadata_json TEXT NOT NULL
                    );
                    """
                )
                connection.execute(
                    "INSERT INTO conversations VALUES (?, NULL, 'standard', NULL)",
                    ("discord:123456",),
                )
                connection.execute(
                    "INSERT INTO conversation_provider_metadata VALUES (?, 'discord', ?)",
                    ("discord:123456", json.dumps({"conversation_type": "dm"})),
                )
                connection.commit()

            actions = DiscordWorkspaceActions(SimpleNamespace(), workspace)
            self.assertTrue(actions.prepare_index())

            with closing(sqlite3.connect(workspace.database_path)) as connection:
                row = connection.execute(
                    "SELECT docx_path, primary_origin_type, primary_origin_id FROM conversations"
                ).fetchone()
            self.assertEqual(row[0], str(docx_path))
            self.assertEqual(row[1], "Direct Messages")
            self.assertEqual(row[2], "123456")
            self.assertEqual(
                actions.resolve_docx_path({"conversation_id": "discord:123456"}),
                docx_path,
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
