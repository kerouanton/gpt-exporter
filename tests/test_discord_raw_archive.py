from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.providers.discord.raw_archive import (
    migrate_plain_raw_file,
    read_raw_bytes,
    read_raw_json,
    write_raw_archive,
)
from gpt_exporter.providers.discord.ui.workspace_actions import DiscordWorkspaceActions
from gpt_exporter.workspaces import ConversationWorkspace


def collector_payload() -> dict:
    return {
        "schema_version": 15,
        "exporter": "9c discord-exporter",
        "exported_at": "2026-09-09T08:00:00.000Z",
        "source_url": "https://discord.com/channels/@me/123456",
        "current_user": {
            "id": "1",
            "display_name": "Gadget MCS",
            "username": "gadgetmcs",
        },
        "conversation": {
            "channel_id": "123456",
            "title": "@soundy",
            "type": "dm",
            "participants": [
                {"id": "1", "name": "Gadget MCS", "username": "gadgetmcs", "is_self": True},
                {"id": "2", "name": "soundy", "username": "soundy", "is_self": False},
            ],
        },
        "message_count": 0,
        "messages": [],
        "diagnostics": {},
        "resources": {"counts": {}},
    }


class DiscordRawArchiveTests(unittest.TestCase):
    def test_xz_round_trip_preserves_exact_original_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "incoming.json"
            original = b'\xef\xbb\xbf{\r\n  "exporter": "9c discord-exporter",  "x": 1\r\n}\r\n'
            source.write_bytes(original)
            destination = temp / "raw.json.xz"

            write_raw_archive(source, destination)

            self.assertNotEqual(destination.read_bytes(), original)
            self.assertEqual(read_raw_bytes(destination), original)

    def test_plain_raw_migration_is_verified_and_removes_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "old.json"
            original = json.dumps(collector_payload(), ensure_ascii=False, indent=4).encode("utf-8")
            source.write_bytes(original)
            destination = temp / "new.json.xz"

            result = migrate_plain_raw_file(source, destination)

            self.assertEqual(result, destination.resolve())
            self.assertFalse(source.exists())
            self.assertEqual(read_raw_bytes(destination), original)
            self.assertEqual(read_raw_json(destination)["conversation"]["channel_id"], "123456")

    def test_workspace_prepare_migrates_existing_human_named_raw_json_without_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Discord Archive"
            raw_dir = root / "raw"
            raw_dir.mkdir(parents=True)
            source = raw_dir / "Discord DM gadgetmcs ↔ soundy 123456.json"
            original = json.dumps(collector_payload(), ensure_ascii=False).encode("utf-8")
            source.write_bytes(original)
            workspace = ConversationWorkspace(
                name="Discord",
                provider_id="discord",
                root_path=root,
            )
            actions = DiscordWorkspaceActions(mock.Mock(), workspace)

            changed = actions.prepare_index()

            destination = raw_dir / "Discord DM gadgetmcs ↔ soundy 123456.json.xz"
            self.assertTrue(changed)
            self.assertFalse(source.exists())
            self.assertTrue(destination.is_file())
            self.assertEqual(read_raw_bytes(destination), original)


if __name__ == "__main__":
    unittest.main()
