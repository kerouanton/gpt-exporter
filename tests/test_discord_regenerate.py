from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from export_provider_discord.archive import archive_collector_export
from export_provider_discord.raw_archive import read_raw_bytes


class DiscordRegenerationTests(unittest.TestCase):
    def test_missing_docx_can_be_regenerated_from_archived_raw_json_xz(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            root = temp / "archive"
            source = temp / "incoming.json"
            source.write_text(
                json.dumps(
                    {
                        "schema_version": 15,
                        "exporter": "9c discord-exporter",
                        "exported_at": "2026-09-09T06:00:00.000Z",
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
                                {"id": "1", "name": "Gadget MCS", "is_self": True},
                                {"id": "2", "name": "soundy", "is_self": False},
                            ],
                        },
                        "message_count": 1,
                        "messages": [
                            {
                                "id": "100",
                                "timestamp": "2026-09-09T06:00:00.000Z",
                                "author": {
                                    "id": "1",
                                    "name": "Gadget MCS",
                                    "is_self": True,
                                    "self_detection": "discord-user-id",
                                },
                                "content": "hello",
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
                        ],
                        "diagnostics": {},
                        "resources": {"counts": {}},
                    }
                ),
                encoding="utf-8",
            )

            def fake_docx(_markdown_path, docx_path, **_kwargs):
                Path(docx_path).write_bytes(b"PK-fake-docx")

            with mock.patch(
                "export_provider_discord.archive.export_docx",
                side_effect=fake_docx,
            ):
                first = archive_collector_export(source, archive_root=root)
                raw_before = read_raw_bytes(first.raw_path)
                first.docx_path.unlink()

                second = archive_collector_export(first.raw_path, archive_root=root)

            self.assertEqual(second.raw_path, first.raw_path)
            self.assertTrue(second.raw_path.name.endswith(".json.xz"))
            self.assertEqual(read_raw_bytes(second.raw_path), raw_before)
            self.assertTrue(second.docx_path.is_file())
            self.assertGreater(second.docx_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
