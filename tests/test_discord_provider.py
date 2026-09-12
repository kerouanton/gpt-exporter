from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.core import CanonicalConversation, ConversationProvider
from export_provider_discord import DiscordProvider
from export_provider_discord.naming import dm_artifact_stem, dm_title


class DiscordProviderTests(unittest.TestCase):
    def test_provider_descriptor_and_contract(self) -> None:
        provider = DiscordProvider()
        self.assertIsInstance(provider, ConversationProvider)
        self.assertEqual(provider.descriptor.provider_id, "discord")
        self.assertEqual(provider.descriptor.display_name, "Discord")

    def test_discovers_and_normalizes_native_json_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            channel = root / "messages" / "123456"
            channel.mkdir(parents=True)
            (channel / "channel.json").write_text(
                json.dumps(
                    {
                        "channel_id": "123456",
                        "channel_name": "general",
                        "guild_id": "guild-1",
                        "guild_name": "Test Server",
                    }
                ),
                encoding="utf-8",
            )
            transcript = channel / "messages.json"
            transcript.write_text(
                json.dumps(
                    [
                        {
                            "ID": "m1",
                            "Timestamp": "2026-09-01T10:00:00+00:00",
                            "Contents": "hello",
                            "Attachments": "https://cdn.discordapp.com/attachments/a/b/image.png",
                        },
                        {
                            "ID": "m2",
                            "Timestamp": "2026-09-01T11:00:00+00:00",
                            "Contents": "world",
                            "Attachments": "",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            provider = DiscordProvider()
            discovered = tuple(provider.discover(root))
            self.assertEqual(discovered, (transcript,))
            conversation = provider.normalize(transcript)

        self.assertIsInstance(conversation, CanonicalConversation)
        self.assertEqual(conversation.provider_id, "discord")
        self.assertEqual(conversation.conversation_id, "discord:123456")
        self.assertEqual(conversation.title, "Test Server / #general")
        self.assertEqual([message.content for message in conversation.messages], ["hello", "world"])
        self.assertEqual([message.role for message in conversation.messages], ["user", "user"])
        self.assertEqual(len(conversation.messages[0].assets), 1)
        self.assertEqual(conversation.messages[0].assets[0].name, "image.png")
        self.assertEqual(conversation.metadata["transcript_format"], "json")

    def test_supports_older_csv_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            channel = Path(temporary) / "messages" / "42"
            channel.mkdir(parents=True)
            transcript = channel / "messages.csv"
            with transcript.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("ID", "Timestamp", "Contents", "Attachments"),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "ID": "old-1",
                        "Timestamp": "2024-01-01T00:00:00+00:00",
                        "Contents": "legacy csv",
                        "Attachments": "",
                    }
                )

            conversation = DiscordProvider().normalize(transcript)

        self.assertEqual(conversation.conversation_id, "discord:42")
        self.assertEqual(conversation.messages[0].content, "legacy csv")
        self.assertEqual(conversation.metadata["transcript_format"], "csv")

    def test_does_not_treat_unrelated_json_as_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            messages = root / "messages"
            messages.mkdir()
            (messages / "index.json").write_text(
                json.dumps({"123": "general"}), encoding="utf-8"
            )
            self.assertEqual(tuple(DiscordProvider().discover(root)), ())

    def test_unresolved_dm_peer_falls_back_to_discord_page_title(self) -> None:
        metadata = {
            "conversation_type": "dm",
            "current_user": {
                "id": "350248805700075521",
                "display_name": "Gadget MCS",
                "is_self": True,
            },
            "participants": [
                {"id": None, "name": None, "avatar_url": None, "is_self": None}
            ],
        }

        title = dm_title(metadata, "(102) Discord | @Zekah")

        self.assertEqual(title, "Gadget MCS ↔ Zekah")
        self.assertEqual(
            dm_artifact_stem(metadata, "1403414893561905163"),
            "Discord DM Gadget MCS ↔ Zekah 1403414893561905163",
        )
        peer = next(
            participant
            for participant in metadata["participants"]
            if participant.get("is_self") is False
        )
        self.assertEqual(peer["name"], "Zekah")
        self.assertEqual(peer["identity_source"], "document-title-fallback")


if __name__ == "__main__":
    unittest.main()
