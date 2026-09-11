from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from gpt_exporter.core.serialization import read_canonical_conversation
from gpt_exporter.providers.discord.archive import archive_collector_export
from gpt_exporter.providers.discord.raw_archive import read_raw_bytes


def payload(message_ids: tuple[str, ...]) -> dict:
    messages = [
        {
            "id": message_id,
            "timestamp": f"2026-09-08T10:{index:02d}:00.000Z",
            "author": {
                "id": "1" if index % 2 == 0 else "2",
                "name": "Bruno" if index % 2 == 0 else "Alice",
                "is_self": index % 2 == 0,
                "self_detection": "discord-user-id",
            },
            "content": f"message {message_id}",
            "content_type": "text",
            "content_types": ["text"],
            "mentions": [],
            "links": [],
            "linked_media": [],
            "attachments": [],
            "external_previews": [],
            "stickers": [],
            "reply": None,
            "reactions": [],
            "edited": False,
            "resource_refs": [],
        }
        for index, message_id in enumerate(message_ids)
    ]
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
            "participants": [],
        },
        "message_count": len(messages),
        "messages": messages,
        "diagnostics": {},
        "resources": {"counts": {}},
    }


class DiscordArchiveTests(unittest.TestCase):
    def test_archives_raw_bytes_and_canonical_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "incoming.json"
            raw_text = json.dumps(payload(("100", "101")), ensure_ascii=False, separators=(",", ":"))
            source.write_text(raw_text, encoding="utf-8")
            root = temp / "archive"

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown") as markdown,
                mock.patch("gpt_exporter.providers.discord.archive.export_docx") as docx,
                mock.patch("gpt_exporter.providers.discord.archive.update_index") as index,
            ):
                result = archive_collector_export(source, archive_root=root)

            self.assertTrue(result.updated)
            self.assertTrue(result.raw_path.name.endswith(".raw.json.xz"))
            self.assertEqual(read_raw_bytes(result.raw_path), source.read_bytes())
            canonical = read_canonical_conversation(result.canonical_path)
            self.assertEqual(canonical.provider_id, "discord")
            self.assertEqual([m.message_id for m in canonical.messages], ["100", "101"])
            self.assertEqual(canonical.metadata["origin_type"], "Direct Messages")
            self.assertEqual(canonical.metadata["origin_id"], "123456")
            markdown.assert_called_once()
            docx.assert_called_once()
            index.assert_called_once()

    def test_dm_uses_human_title_filename_and_author_avatars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            data = payload(("100", "101"))
            data["current_user"] = {
                "id": "1",
                "display_name": "Gadget MCS",
                "username": "gadgetmcs",
                "avatar_url": "https://cdn.discordapp.com/avatars/1/self.webp?size=80",
            }
            data["conversation"]["title"] = "(117) Discord | @soundy"
            data["conversation"]["participants"] = [
                {
                    "id": "2",
                    "name": "soundy",
                    "avatar_url": "https://cdn.discordapp.com/avatars/2/peer.webp?size=80",
                    "is_self": False,
                },
                {
                    "id": "1",
                    "name": "Gadget MCS",
                    "avatar_url": "https://cdn.discordapp.com/avatars/1/self.webp?size=80",
                    "is_self": True,
                },
            ]
            source = temp / "incoming.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            root = temp / "archive"

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown"),
                mock.patch("gpt_exporter.providers.discord.archive.export_docx"),
                mock.patch("gpt_exporter.providers.discord.archive.update_index"),
                mock.patch("gpt_exporter.providers.discord.archive.download_conversation_assets") as downloader,
            ):
                downloader.return_value.available = 0
                downloader.return_value.downloaded = 0
                downloader.return_value.reused = 0
                downloader.return_value.failed = ()
                downloader.return_value.source_paths = {}
                result = archive_collector_export(source, archive_root=root)

            stem = "Discord DM Gadget MCS ↔ soundy 123456"
            self.assertEqual(result.raw_path.name, f"{stem}.raw.json.xz")
            self.assertEqual(result.canonical_path.name, f"{stem}.canonical.json.xz")
            self.assertEqual(result.docx_path.name, f"{stem}.docx")
            canonical = read_canonical_conversation(result.canonical_path)
            self.assertEqual(canonical.title, "Gadget MCS ↔ soundy")
            avatar_assets = [
                asset
                for message in canonical.messages
                for asset in message.assets
                if asset.metadata.get("kind") == "author-avatar"
            ]
            self.assertEqual(len(avatar_assets), 2)
            self.assertTrue(all(asset.media_type == "image/webp" for asset in avatar_assets))

    def test_archive_records_docx_and_direct_message_origin_in_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "incoming.json"
            source.write_text(json.dumps(payload(("100", "101"))), encoding="utf-8")
            root = temp / "archive"

            def fake_docx(_markdown_path, docx_path, **_kwargs):
                Path(docx_path).write_bytes(b"PK-fake-docx")

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown"),
                mock.patch("gpt_exporter.providers.discord.archive.export_docx", side_effect=fake_docx),
            ):
                result = archive_collector_export(source, archive_root=root)

            with closing(sqlite3.connect(result.database_path)) as connection:
                row = connection.execute(
                    """
                    SELECT docx_path, primary_origin_type, primary_origin_id
                    FROM conversations WHERE conversation_id = 'discord:123456'
                    """
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], str(result.docx_path))
            self.assertEqual(row[1], "Direct Messages")
            self.assertEqual(row[2], "123456")

    def test_verified_snapshot_outside_known_range_preserves_missing_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            root = temp / "archive"
            complete_payload = payload(("100", "101", "102"))
            complete_payload["diagnostics"] = {"history_complete": True}
            complete = temp / "complete.json"
            complete.write_text(json.dumps(complete_payload), encoding="utf-8")

            recapture_payload = payload(("101", "102"))
            recapture_payload["diagnostics"] = {"history_complete": True}
            recapture = temp / "recapture.json"
            recapture.write_text(json.dumps(recapture_payload), encoding="utf-8")

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown"),
                mock.patch("gpt_exporter.providers.discord.archive.export_docx"),
                mock.patch("gpt_exporter.providers.discord.archive.update_index"),
            ):
                archive_collector_export(complete, archive_root=root)
                second = archive_collector_export(recapture, archive_root=root)

            self.assertTrue(second.updated)
            self.assertEqual(read_raw_bytes(second.raw_path), recapture.read_bytes())
            canonical = read_canonical_conversation(second.canonical_path)
            self.assertEqual([m.message_id for m in canonical.messages], ["100", "101", "102"])
            self.assertNotIn("deleted", canonical.messages[0].metadata)
            self.assertEqual(canonical.messages[0].content, "message 100")
            self.assertEqual(canonical.metadata["snapshot_coverage"], "complete-outside-known-range")


if __name__ == "__main__":
    unittest.main()
