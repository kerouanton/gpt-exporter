from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage
from gpt_exporter.export.docx import export_docx
from export_provider_discord.archive import (
    _participant_label,
    _participant_records,
    _prepend_dm_participant_header,
    _without_author_avatars,
)


class DiscordDocxHeaderTests(unittest.TestCase):
    def test_compact_header_renders_two_inline_avatars_and_display_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self_avatar = root / "avatar-self.png"
            peer_avatar = root / "avatar-peer.png"
            Image.new("RGB", (24, 24), (255, 255, 255)).save(self_avatar)
            Image.new("RGB", (24, 24), (0, 0, 0)).save(peer_avatar)

            markdown = root / "conversation.md"
            markdown.write_text(
                "![Conversation participant avatar: Gadget MCS](avatar-self.png) "
                "![Conversation participant avatar: soundy](avatar-peer.png)\n\n"
                "---\n\n"
                "**2026-09-09**\n\n"
                "**soundy**\n\n"
                "**21:52**  hello\n",
                encoding="utf-8",
            )
            output = root / "conversation.docx"
            progress: list[str] = []
            export_docx(markdown, output, overwrite=True, progress=progress.append)

            document = Document(output)
            header = next(
                paragraph
                for paragraph in document.paragraphs
                if "Gadget MCS" in paragraph.text
            )
            self.assertIn("↔", header.text)
            self.assertIn("soundy", header.text)
            self.assertNotIn("@gadgetmcs", header.text)
            self.assertGreaterEqual(len(header._p.xpath(".//w:drawing")), 2)
            self.assertTrue(any("initial document saved" in line for line in progress))
            self.assertTrue(any("chat metadata styles complete" in line for line in progress))
            self.assertTrue(any("DOCX processing complete" in line for line in progress))

    def test_archive_keeps_avatars_but_export_body_drops_them(self) -> None:
        avatar = CanonicalAsset(
            asset_id="discord:author-avatar:1",
            name="avatar-1.webp",
            media_type="image/webp",
            source_ref="https://cdn.discordapp.com/avatars/1/a.webp",
            metadata={"kind": "author-avatar"},
        )
        attachment = CanonicalAsset(
            asset_id="discord:attachment:1",
            name="file.txt",
            source_ref="file.txt",
            metadata={"kind": "attachment"},
        )
        conversation = CanonicalConversation(
            conversation_id="discord:123",
            provider_id="discord",
            title="@soundy",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    author_id="1",
                    author_name="Gadget MCS",
                    content="hello",
                    assets=(avatar, attachment),
                ),
            ),
            metadata={
                "current_user": {
                    "id": "1",
                    "username": "gadgetmcs",
                    "display_name": "Gadget MCS",
                    "is_self": True,
                },
                "participants": [
                    {
                        "id": "1",
                        "name": "Gadget MCS",
                        "is_self": True,
                    },
                    {
                        "id": "2",
                        "name": "soundy",
                        "is_self": False,
                    },
                ],
            },
        )

        stripped = _without_author_avatars(conversation)
        self.assertEqual([asset.metadata.get("kind") for asset in stripped.messages[0].assets], ["attachment"])

        records = _participant_records(conversation)
        self.assertEqual(_participant_label(records[0]), "Gadget MCS")
        self.assertEqual(_participant_label(records[1]), "soundy")

    def test_empty_placeholder_participant_is_omitted_from_dm_header(self) -> None:
        conversation = CanonicalConversation(
            conversation_id="discord:994497416583708703",
            provider_id="discord",
            title="Gadget MCS ↔ Littleloulita",
            messages=(),
            metadata={
                "current_user": {
                    "id": "1",
                    "username": "gadgetmcs",
                    "display_name": "Gadget MCS",
                    "is_self": True,
                },
                "participants": [
                    {"id": "1", "name": "Gadget MCS", "is_self": True},
                    {"id": "2", "name": "Littleloulita", "is_self": False},
                    {
                        "id": None,
                        "username": None,
                        "display_name": None,
                        "name": None,
                        "avatar_url": None,
                        "is_self": False,
                    },
                ],
            },
        )

        records = _participant_records(conversation)
        labels = [_participant_label(record) for record in records]
        self.assertEqual(labels, ["Gadget MCS", "Littleloulita"])
        self.assertNotIn("Unknown participant", labels)

    def test_prepend_header_keeps_body_and_uses_local_avatar_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown = root / "conversation.md"
            markdown.write_text("BODY\n", encoding="utf-8")
            self_avatar = root / "self.webp"
            peer_avatar = root / "peer.webp"
            self_avatar.write_bytes(b"self")
            peer_avatar.write_bytes(b"peer")
            self_url = "https://cdn.discordapp.com/avatars/1/self.webp"
            peer_url = "https://cdn.discordapp.com/avatars/2/peer.webp"
            conversation = CanonicalConversation(
                conversation_id="discord:123",
                provider_id="discord",
                title="@soundy",
                messages=(),
                metadata={
                    "current_user": {
                        "id": "1",
                        "username": "gadgetmcs",
                        "display_name": "Gadget MCS",
                        "avatar_url": self_url,
                    },
                    "participants": [
                        {"id": "1", "name": "Gadget MCS", "avatar_url": self_url, "is_self": True},
                        {"id": "2", "name": "soundy", "avatar_url": peer_url, "is_self": False},
                    ],
                },
            )
            _prepend_dm_participant_header(
                markdown,
                conversation,
                {self_url: self_avatar, peer_url: peer_avatar},
            )
            text = markdown.read_text(encoding="utf-8")
            self.assertIn("Conversation participant avatar: Gadget MCS", text)
            self.assertIn("Conversation participant avatar: soundy", text)
            self.assertNotIn("@gadgetmcs", text)
            self.assertTrue(text.rstrip().endswith("BODY"))


if __name__ == "__main__":
    unittest.main()
