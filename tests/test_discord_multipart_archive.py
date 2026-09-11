from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.providers.discord.archive import archive_collector_export


def _payload() -> dict:
    messages = []
    for index in range(10):
        messages.append(
            {
                "id": f"old-{index}",
                "timestamp": f"2025-12-{index + 1:02d}T10:00:00.000Z",
                "author": {"id": "1", "name": "A", "is_self": True},
                "content": f"old {index}",
                "attachments": [],
                "linked_media": [],
                "external_previews": [],
                "stickers": [],
            }
        )
    for index in range(1000):
        day = index % 28 + 1
        messages.append(
            {
                "id": f"new-{index}",
                "timestamp": f"2026-01-{day:02d}T10:00:00.000Z",
                "author": {"id": "2", "name": "B", "is_self": False},
                "content": f"new {index}",
                "attachments": [],
                "linked_media": [],
                "external_previews": [],
                "stickers": [],
            }
        )
    return {
        "schema_version": 15,
        "exporter": "9c discord-exporter",
        "exported_at": "2026-09-10T10:00:00.000Z",
        "source_url": "https://discord.com/channels/@me/123456",
        "current_user": {"id": "1", "display_name": "A"},
        "conversation": {
            "channel_id": "123456",
            "title": "B - Discord",
            "type": "dm",
            "participants": [
                {"id": "1", "name": "A", "display_name": "A", "is_self": True},
                {"id": "2", "name": "B", "display_name": "B", "is_self": False},
            ],
        },
        "message_count": len(messages),
        "messages": messages,
        "diagnostics": {},
        "resources": {"counts": {}},
    }


class DiscordMultipartArchiveTests(unittest.TestCase):
    def test_archive_renders_each_planned_part_and_tracks_latest_part(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            source = temp / "incoming.json"
            source.write_text(json.dumps(_payload()), encoding="utf-8")
            root = temp / "archive"

            with (
                mock.patch("gpt_exporter.providers.discord.archive.export_canonical_markdown") as markdown,
                mock.patch("gpt_exporter.providers.discord.archive.export_docx") as docx,
                mock.patch("gpt_exporter.providers.discord.archive.update_index"),
            ):
                result = archive_collector_export(source, archive_root=root)

            self.assertEqual(
                [path.name for path in result.docx_paths],
                [
                    "Discord DM A ↔ B 123456 - 2025.docx",
                    "Discord DM A ↔ B 123456 - 2026Q1.docx",
                ],
            )
            self.assertEqual(result.docx_path, result.docx_paths[-1])
            self.assertEqual(markdown.call_count, 2)
            self.assertEqual(docx.call_count, 2)


if __name__ == "__main__":
    unittest.main()
