from __future__ import annotations

import base64
import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z6f8AAAAASUVORK5CYII="
)


class InlineAvatarAuthorTests(unittest.TestCase):
    def test_avatar_and_author_share_one_docx_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            avatar_path = root / "avatar-2.png"
            avatar_path.write_bytes(_PNG_1X1)

            avatar = CanonicalAsset(
                asset_id="discord:avatar:2",
                name="avatar-2.png",
                media_type="image/png",
                source_ref=str(avatar_path),
                metadata={"kind": "author-avatar"},
            )
            conversation = CanonicalConversation(
                conversation_id="discord:inline-avatar",
                provider_id="discord",
                title="inline avatar",
                messages=(
                    CanonicalMessage(
                        message_id="1",
                        role="other",
                        author_id="2",
                        author_name="soundy",
                        created_at="2026-05-06T13:20:54",
                        content="hello",
                        assets=(avatar,),
                    ),
                ),
            )

            markdown_path = root / "conversation.md"
            export_canonical_markdown(
                conversation,
                markdown_path,
                include_timestamps=True,
                include_title=False,
                chat_style=True,
            )
            docx_path = root / "conversation.docx"
            export_docx(
                markdown_path,
                docx_path,
                document_title="inline avatar",
                overwrite=True,
            )

            with zipfile.ZipFile(docx_path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8")

        avatar_marker = 'descr="Author avatar: soundy"'
        self.assertIn(avatar_marker, document_xml)
        avatar_pos = document_xml.index(avatar_marker)
        paragraph_start = document_xml.rfind("<w:p", 0, avatar_pos)
        paragraph_end = document_xml.index("</w:p>", avatar_pos)
        avatar_paragraph = document_xml[paragraph_start:paragraph_end]
        self.assertIn("soundy", avatar_paragraph)
        self.assertIn('w:val="2F75B5"', avatar_paragraph)


if __name__ == "__main__":
    unittest.main()
