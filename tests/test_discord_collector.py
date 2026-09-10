from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.core import CanonicalConversation
from gpt_exporter.providers.discord.collector import (
    collector_javascript,
    snapshot_exports,
    validate_collector_export,
    wait_for_new_export,
)
from gpt_exporter.providers.discord.provider import DiscordProvider


def collector_payload(*, message_ids=("100", "101")) -> dict:
    messages = []
    for index, message_id in enumerate(message_ids):
        self_message = index % 2 == 0
        messages.append(
            {
                "id": message_id,
                "timestamp": f"2026-09-08T10:0{index}:00.000Z",
                "author": {
                    "id": "1" if self_message else "2",
                    "name": "Bruno" if self_message else "Alice",
                    "is_self": self_message,
                    "self_detection": "discord-user-id",
                },
                "content": "hello" if self_message else "reply",
                "content_type": "text",
                "content_types": ["text"],
                "mentions": [],
                "links": [],
                "linked_media": [],
                "attachments": (
                    [
                        {
                            "id": "900",
                            "name": "image.png",
                            "kind": "image",
                            "original_url": "https://cdn.discordapp.com/attachments/10/900/image.png",
                            "preview_url": None,
                        }
                    ]
                    if self_message
                    else []
                ),
                "external_previews": [],
                "stickers": [],
                "reply": None,
                "reactions": [],
                "edited": False,
                "resource_refs": [],
            }
        )
    return {
        "schema_version": 15,
        "exporter": "9c discord-exporter",
        "exported_at": "2026-09-08T10:10:00.000Z",
        "source_url": "https://discord.com/channels/@me/123456",
        "current_user": {"id": "1", "display_name": "Bruno"},
        "conversation": {
            "channel_id": "123456",
            "title": "Alice - Discord",
            "type": "dm",
            "participants": [
                {"id": "1", "name": "Bruno", "is_self": True},
                {"id": "2", "name": "Alice", "is_self": False},
            ],
        },
        "message_count": len(messages),
        "self_message_count": sum(m["author"]["is_self"] is True for m in messages),
        "other_message_count": sum(m["author"]["is_self"] is False for m in messages),
        "unresolved_author_count": 0,
        "diagnostics": {},
        "resources": {"counts": {"attachments": 1}},
        "messages": messages,
    }


class DiscordCollectorTests(unittest.TestCase):
    def test_packaged_collector_is_the_validated_v15_script(self) -> None:
        script = collector_javascript()
        self.assertIn('schema_version: 15', script)
        self.assertIn('exporter: "9c discord-exporter"', script)
        self.assertIn('discord-dm-export-v15_', script)
        self.assertIn('history_complete:', script)
        self.assertIn('reached_top_of_conversation:', script)
        self.assertIn('top_of_history_marker_detected:', script)
        self.assertIn('Beginning evidence', script)

    def test_validate_and_normalize_full_dm_collector_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "discord-dm-export-v15_123456_test.json"
            payload = collector_payload()
            payload["diagnostics"] = {
                "history_complete": True,
                "reached_top_of_conversation": True,
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            summary = validate_collector_export(path)
            conversation = DiscordProvider().normalize(path)

        self.assertEqual(summary.channel_id, "123456")
        self.assertEqual(summary.message_count, 2)
        self.assertIsInstance(conversation, CanonicalConversation)
        self.assertEqual(conversation.conversation_id, "discord:123456")
        self.assertEqual([message.role for message in conversation.messages], ["user", "other"])
        self.assertEqual([message.author_name for message in conversation.messages], ["Bruno", "Alice"])
        self.assertEqual(conversation.messages[0].assets[0].name, "image.png")
        self.assertEqual(conversation.metadata["source_kind"], "browser_collector")
        self.assertTrue(conversation.metadata["diagnostics"]["history_complete"])
        self.assertTrue(conversation.metadata["diagnostics"]["reached_top_of_conversation"])

    def test_snapshot_and_wait_ignore_existing_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "discord-dm-export-v15_123456_old.json"
            existing.write_text(json.dumps(collector_payload()), encoding="utf-8")
            known = snapshot_exports(root)
            self.assertEqual(known, {existing.resolve()})

            fresh = root / "discord-dm-export-v15_123456_new.json"
            fresh.write_text(json.dumps(collector_payload()), encoding="utf-8")
            summary = wait_for_new_export(root, known_files=known, timeout_seconds=0.2, poll_seconds=0.01)
            self.assertEqual(summary.path, fresh.resolve())

    def test_invalid_or_partial_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "discord-dm-export-v15_123456_bad.json"
            payload = collector_payload()
            payload["message_count"] = 999
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "message count mismatch"):
                validate_collector_export(path)


if __name__ == "__main__":
    unittest.main()
