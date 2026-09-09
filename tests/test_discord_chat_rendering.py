from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown, render_canonical_markdown
from gpt_exporter.providers.discord.collector import collector_javascript


def conversation() -> CanonicalConversation:
    return CanonicalConversation(
        conversation_id="discord:123",
        provider_id="discord",
        title="@soundy",
        messages=(
            CanonicalMessage(
                message_id="1",
                role="other",
                author_id="2",
                author_name="soundy",
                created_at="2026-05-06T13:20:54",
                content="Salut Bruno! 😉\nDeuxième ligne",
                metadata={
                    "preserve_line_breaks": True,
                    "edited": True,
                    "reply": {
                        "message_id": "0",
                        "author": "Gadget MCS",
                        "text": "message précédent",
                        "url": "https://discord.com/channels/@me/123/0",
                    },
                    "reactions": [
                        {"emoji": "👍", "count": 1},
                        {"emoji": "🥰", "count": 2},
                    ],
                    "link_previews": [
                        {
                            "site_name": "pouet.net",
                            "title": "This is PSX by New Generation Crew",
                            "description": "demo for Playstation, 4th at Revision 2024",
                            "url": "https://www.pouet.net/prod.php?which=96590",
                        }
                    ],
                },
            ),
            CanonicalMessage(
                message_id="2",
                role="other",
                author_id="2",
                author_name="soundy",
                created_at="2026-05-06T13:21:10",
                content="#pragma once\n// line one\n// line two",
                metadata={"preserve_line_breaks": True},
            ),
            CanonicalMessage(
                message_id="3",
                role="user",
                author_id="1",
                author_name="Gadget MCS",
                created_at="2026-05-07T09:46:20",
                content="Merci!",
                metadata={"preserve_line_breaks": True},
            ),
        ),
    )


class DiscordChatRenderingTests(unittest.TestCase):
    def test_collector_overlay_preserves_inline_emoji_alt_text(self) -> None:
        source = collector_javascript()
        self.assertIn('clone.querySelectorAll("img[alt]")', source)
        self.assertIn('image.replaceWith(alt)', source)

    def test_canonical_markdown_uses_compact_chat_semantics(self) -> None:
        markdown = render_canonical_markdown(
            conversation(),
            include_timestamps=True,
            include_title=False,
        )
        self.assertNotIn("# @soundy", markdown)
        self.assertEqual(markdown.count("**soundy**"), 1)
        self.assertIn("**soundy**  *13:20 · edited*", markdown)
        self.assertIn("*13:21*", markdown)
        self.assertIn("Salut Bruno! 😉  \nDeuxième ligne", markdown)
        self.assertIn("#pragma once  \n// line one  \n// line two", markdown)
        self.assertIn("👍 1   🥰 2", markdown)
        self.assertIn("↪ **Gadget MCS**", markdown)
        self.assertIn("**pouet.net**", markdown)
        self.assertIn("This is PSX by New Generation Crew", markdown)
        self.assertIn("**2026-05-06**", markdown)
        self.assertIn("**2026-05-07**", markdown)

    def test_docx_preserves_emoji_and_semantic_line_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown_path = root / "conversation.md"
            export_canonical_markdown(
                conversation(),
                markdown_path,
                include_timestamps=True,
                include_title=False,
            )
            docx_path = root / "conversation.docx"
            export_docx(
                markdown_path,
                docx_path,
                document_title="@soundy",
                overwrite=True,
            )
            with zipfile.ZipFile(docx_path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("😉", document_xml)
        self.assertIn("👍", document_xml)
        self.assertIn("🥰", document_xml)
        self.assertIn("<w:br", document_xml)
        self.assertEqual(document_xml.count("@soundy"), 1)


if __name__ == "__main__":
    unittest.main()
