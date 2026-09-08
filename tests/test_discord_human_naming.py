from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.providers.discord.archive import archive_collector_export
from gpt_exporter.providers.discord.ui.workspace_actions import DiscordWorkspaceActions
from gpt_exporter.workspaces import ConversationWorkspace


def payload(*, username: str, peer: str, message_ids: tuple[str, ...]) -> dict:
    messages = []
    for index, message_id in enumerate(message_ids):
        is_self = index % 2 == 0
        messages.append(
            {
                "id": message_id,
                "timestamp": f"2026-09-08T10:{index:02d}:00.000Z",
                "author": {
                    "id": "1" if is_self else "2",
                    "name": "Gadget MCS" if is_self else peer,
                    "is_self": is_self,
                    "self_detection": "discord-user-id",
                },
                "content": message_id,
                "attachments": [],
                "linked_media": [],
                "external_previews": [],
                "stickers": [],
            }
        )
    return {
        "schema_version": 15,
        "exporter": "9c discord-exporter",
        "current_user": {"id": "1", "display_name": "Gadget MCS", "username": username},
        "conversation": {
            "channel_id": "123456",
            "title": f"Discord | @{peer}",
            "type": "dm",
            "participants": [
                {"id": "2", "name": peer, "is_self": False},
                {"id": "1", "name": "Gadget MCS", "is_self": True},
            ],
        },
        "messages": messages,
    }


class DiscordHumanNamingTests(unittest.TestCase):
    def test_username_change_still_finds_complete_prior_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "archive"
            first = Path(temporary) / "first.json"
            first.write_text(
                json.dumps(payload(username="gadgetmcs", peer="soundy", message_ids=("100", "101", "102"))),
                encoding="utf-8",
            )
            second = Path(temporary) / "second.json"
            second.write_text(
                json.dumps(payload(username="gadgetmcs2", peer="soundy2", message_ids=("101", "102"))),
                encoding="utf-8",
            )

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown"),
                mock.patch("gpt_exporter.providers.discord.archive.export_docx"),
                mock.patch("gpt_exporter.providers.discord.archive.update_index"),
            ):
                original = archive_collector_export(first, archive_root=root)
                partial = archive_collector_export(second, archive_root=root)

            self.assertTrue(original.updated)
            self.assertFalse(partial.updated)
            self.assertEqual(partial.message_count, 3)
            self.assertEqual(
                partial.canonical_path.name,
                "Discord DM gadgetmcs2 ↔ soundy2 123456.json.xz",
            )
            candidates = list((root / "downloads").glob("*123456.json.xz"))
            self.assertEqual(candidates, [partial.canonical_path])

    def test_prepare_index_keeps_missing_docx_path_null(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = ConversationWorkspace("Discord", "discord", root)
            metadata = {
                "conversation_type": "dm",
                "current_user": {"id": "1", "username": "gadgetmcs"},
                "participants": [{"id": "2", "name": "soundy", "is_self": False}],
            }
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
                    """
                )
                connection.execute(
                    "INSERT INTO conversations VALUES (?, ?, ?, NULL, 'standard', NULL)",
                    ("discord:123456", "Discord | @soundy", "missing.json.xz"),
                )
                connection.execute(
                    "INSERT INTO conversation_provider_metadata VALUES (?, 'discord', ?)",
                    ("discord:123456", json.dumps(metadata)),
                )
                connection.commit()

            actions = DiscordWorkspaceActions(SimpleNamespace(), workspace)
            self.assertTrue(actions.prepare_index())
            with closing(sqlite3.connect(workspace.database_path)) as connection:
                row = connection.execute("SELECT docx_path FROM conversations").fetchone()
            self.assertIsNone(row[0])


if __name__ == "__main__":
    unittest.main()
