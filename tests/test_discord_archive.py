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
            self.assertEqual(result.raw_path.read_bytes(), source.read_bytes())
            canonical = read_canonical_conversation(result.canonical_path)
            self.assertEqual(canonical.provider_id, "discord")
            self.assertEqual([m.message_id for m in canonical.messages], ["100", "101"])
            self.assertEqual(canonical.metadata["origin_type"], "Direct Messages")
            self.assertEqual(canonical.metadata["origin_id"], "123456")
            markdown.assert_called_once()
            docx.assert_called_once()
            index.assert_called_once()

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

    def test_partial_collector_export_cannot_replace_complete_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            root = temp / "archive"
            complete = temp / "complete.json"
            complete.write_text(json.dumps(payload(("100", "101", "102"))), encoding="utf-8")
            partial = temp / "partial.json"
            partial.write_text(json.dumps(payload(("101", "102"))), encoding="utf-8")

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown"),
                mock.patch("gpt_exporter.providers.discord.archive.export_docx"),
                mock.patch("gpt_exporter.providers.discord.archive.update_index"),
            ):
                first = archive_collector_export(complete, archive_root=root)
                raw_before = first.raw_path.read_bytes()
                second = archive_collector_export(partial, archive_root=root)

            self.assertFalse(second.updated)
            self.assertEqual(second.raw_path.read_bytes(), raw_before)
            canonical = read_canonical_conversation(second.canonical_path)
            self.assertEqual([m.message_id for m in canonical.messages], ["100", "101", "102"])


if __name__ == "__main__":
    unittest.main()
