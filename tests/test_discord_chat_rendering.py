from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown, render_canonical_markdown
from export_provider_discord.collector import collector_javascript


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
            chat_style=True,
        )
        self.assertNotIn("# @soundy", markdown)
        self.assertEqual(markdown.count("**soundy**"), 1)
        self.assertIn("**soundy**\n", markdown)
        self.assertIn("**13:20 · edited**", markdown)
        self.assertIn("**13:21**  #pragma once", markdown)
        self.assertIn("// line one  \n// line two", markdown)
        self.assertIn("👍 1   🥰 2", markdown)
        self.assertIn("↪ **Gadget MCS**", markdown)
        self.assertIn("**pouet.net**", markdown)
        self.assertIn("This is PSX by New Generation Crew", markdown)
        self.assertIn("**2026-05-06**", markdown)
        self.assertIn("**2026-05-07**", markdown)

    def test_chat_style_respects_timestamp_opt_out(self) -> None:
        markdown = render_canonical_markdown(
            conversation(),
            include_timestamps=False,
            include_title=False,
            chat_style=True,
        )
        self.assertNotIn("2026-05-06", markdown)
        self.assertNotIn("13:20", markdown)

    def test_preview_asset_without_rich_metadata_is_not_dropped(self) -> None:
        preview = CanonicalAsset(
            asset_id="preview:1",
            name="preview.jpg",
            media_type="image/jpeg",
            source_ref="preview.jpg",
            metadata={"kind": "external-preview"},
        )
        conv = CanonicalConversation(
            conversation_id="discord:preview",
            provider_id="discord",
            title="preview",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="other",
                    content="link",
                    assets=(preview,),
                    metadata={"preserve_line_breaks": True},
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("![preview.jpg](preview.jpg)", markdown)

    def test_preview_assets_match_explicit_preview_indexes(self) -> None:
        image = CanonicalAsset(
            asset_id="preview:second",
            name="second.jpg",
            media_type="image/jpeg",
            source_ref="second.jpg",
            metadata={"kind": "external-preview", "link_preview_index": 1},
        )
        conv = CanonicalConversation(
            conversation_id="discord:previews",
            provider_id="discord",
            title="previews",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="other",
                    content="two previews",
                    assets=(image,),
                    metadata={
                        "preserve_line_breaks": True,
                        "link_previews": [
                            {"title": "First", "url": "https://example.test/first"},
                            {"title": "Second", "url": "https://example.test/second"},
                        ],
                    },
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        first = markdown.index("[First]")
        second = markdown.index("[Second]")
        image_pos = markdown.index("![second.jpg](second.jpg)")
        self.assertLess(first, second)
        self.assertLess(second, image_pos)
        self.assertEqual(markdown.count("second.jpg"), 2)

    def test_bare_url_and_email_become_clickable_markdown_autolinks(self) -> None:
        conv = CanonicalConversation(
            conversation_id="discord:links",
            provider_id="discord",
            title="links",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content=(
                        "contact https://www.linkedin.com/company/digisquad-luxembourg/ "
                        "info@digisquad.com"
                    ),
                    metadata={"preserve_line_breaks": True},
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("<https://www.linkedin.com/company/digisquad-luxembourg/>", markdown)
        self.assertIn("<info@digisquad.com>", markdown)

    def test_parenthesized_bare_url_is_linked_but_markdown_target_is_not_rewritten(self) -> None:
        conv = CanonicalConversation(
            conversation_id="discord:parenthesized-link",
            provider_id="discord",
            title="links",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content=(
                        "Claude (https://www.pouet.net/prod.php?which=96590) rien de fou\n"
                        "[existing](https://example.test/already)"
                    ),
                    metadata={"preserve_line_breaks": True},
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("(<https://www.pouet.net/prod.php?which=96590>)", markdown)
        self.assertIn("[existing](https://example.test/already)", markdown)
        self.assertNotIn("[existing](<https://example.test/already>)", markdown)

    def test_autolink_does_not_touch_fenced_or_inline_code(self) -> None:
        conv = CanonicalConversation(
            conversation_id="discord:code-links",
            provider_id="discord",
            title="code",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content=(
                        "`https://inline.example/`\n"
                        "```text\nhttps://fenced.example/\n```\n"
                        "https://outside.example/"
                    ),
                    metadata={"preserve_line_breaks": True},
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("`https://inline.example/`", markdown)
        self.assertIn("https://fenced.example/", markdown)
        self.assertNotIn("<https://fenced.example/>", markdown)
        self.assertIn("<https://outside.example/>", markdown)

    def test_media_aliases_are_deduplicated_but_distinct_attachments_are_kept(self) -> None:
        linked = CanonicalAsset(
            asset_id="linked:1",
            name="clip.mp4",
            source_ref="assets/a_clip.mp4",
            metadata={"kind": "linked-media"},
        )
        preview_alias = CanonicalAsset(
            asset_id="preview:1",
            name="clip.mp4",
            source_ref="assets/b_clip.mp4",
            metadata={"kind": "external-preview"},
        )
        first_attachment = CanonicalAsset(
            asset_id="attachment:1",
            name="same.bin",
            source_ref="assets/one_same.bin",
            metadata={"kind": "attachment"},
        )
        second_attachment = CanonicalAsset(
            asset_id="attachment:2",
            name="same.bin",
            source_ref="assets/two_same.bin",
            metadata={"kind": "attachment"},
        )
        conv = CanonicalConversation(
            conversation_id="discord:assets",
            provider_id="discord",
            title="assets",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content="media",
                    assets=(linked, preview_alias, first_attachment, second_attachment),
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertEqual(markdown.count("[clip.mp4]"), 1)
        self.assertEqual(markdown.count("[same.bin]"), 2)

    def test_local_archived_attachment_exposes_asset_id_and_archive_path(self) -> None:
        attachment = CanonicalAsset(
            asset_id="discord:attachment:42",
            name="manual.pdf",
            media_type="application/pdf",
            source_ref="../assets/attachment/abc_manual.pdf",
            metadata={
                "kind": "attachment",
                "local_archive_asset": True,
                "archive_path": "assets/attachment/abc_manual.pdf",
            },
        )
        conv = CanonicalConversation(
            conversation_id="discord:attachment",
            provider_id="discord",
            title="attachment",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content="doc",
                    assets=(attachment,),
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("Archived attachment", markdown)
        self.assertIn("manual.pdf", markdown)
        self.assertIn("discord:attachment:42", markdown)
        self.assertIn("assets/attachment/abc_manual.pdf", markdown)

    def test_placeholder_unknown_preview_description_is_suppressed(self) -> None:
        conv = CanonicalConversation(
            conversation_id="discord:unknown-preview",
            provider_id="discord",
            title="preview",
            messages=(
                CanonicalMessage(
                    message_id="1",
                    role="user",
                    content="preview",
                    metadata={
                        "link_previews": [
                            {
                                "title": "HackGyver 2.0",
                                "description": "unknown",
                                "url": "https://example.test/hackgyver",
                            }
                        ]
                    },
                ),
            ),
        )
        markdown = render_canonical_markdown(conv, chat_style=True)
        self.assertIn("HackGyver 2.0", markdown)
        self.assertNotIn("unknown", markdown.casefold())

    def test_docx_preserves_emoji_line_breaks_and_styles_chat_metadata_blue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            markdown_path = root / "conversation.md"
            export_canonical_markdown(
                conversation(),
                markdown_path,
                include_timestamps=True,
                include_title=False,
                chat_style=True,
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
        self.assertIn('w:val="2F75B5"', document_xml)

    def test_bare_http_url_is_a_real_docx_hyperlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conv = CanonicalConversation(
                conversation_id="discord:docx-link",
                provider_id="discord",
                title="links",
                messages=(
                    CanonicalMessage(
                        message_id="1",
                        role="user",
                        content="https://example.test/path",
                    ),
                ),
            )
            markdown_path = root / "conversation.md"
            export_canonical_markdown(conv, markdown_path, chat_style=True)
            docx_path = root / "conversation.docx"
            export_docx(markdown_path, docx_path, document_title="links", overwrite=True)
            with zipfile.ZipFile(docx_path) as archive:
                relationships = archive.read("word/_rels/document.xml.rels").decode("utf-8")
        self.assertIn('Target="https://example.test/path"', relationships)


if __name__ == "__main__":
    unittest.main()
