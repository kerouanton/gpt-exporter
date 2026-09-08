from __future__ import annotations

import base64
import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.core import CanonicalAsset, CanonicalConversation, CanonicalMessage
from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_canonical_markdown
from gpt_exporter.providers.discord.assets import (
    conversation_with_local_assets,
    download_conversation_assets,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def conversation() -> CanonicalConversation:
    return CanonicalConversation(
        conversation_id="discord:123",
        provider_id="discord",
        title="Discord test",
        messages=(
            CanonicalMessage(
                message_id="1",
                role="user",
                author_name="Bruno",
                content="image follows",
                assets=(
                    CanonicalAsset(
                        asset_id="discord:attachment:999",
                        name="capture.png",
                        source_ref="https://cdn.discordapp.com/attachments/123/999/capture.png?sig=test",
                        metadata={"provider": "discord", "kind": "attachment"},
                    ),
                ),
            ),
        ),
    )


class DiscordAssetTests(unittest.TestCase):
    def test_download_localize_and_embed_image_in_docx(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets" / "123"
            markdown_dir = root / ".markdown"
            markdown_dir.mkdir()

            result = download_conversation_assets(
                conversation(),
                assets,
                fetch_bytes=lambda _url: PNG_1X1,
            )
            self.assertEqual(result.downloaded, 1)
            self.assertEqual(result.available, 1)
            self.assertEqual(result.failed, ())

            localized = conversation_with_local_assets(
                conversation(),
                result.source_paths,
                relative_to=markdown_dir,
            )
            local_ref = localized.messages[0].assets[0].source_ref
            self.assertIsNotNone(local_ref)
            self.assertFalse(str(local_ref).startswith("http"))
            self.assertIn("assets/123", str(local_ref).replace("\\", "/"))

            markdown = markdown_dir / "conversation.md"
            export_canonical_markdown(localized, markdown, include_timestamps=True)
            markdown_text = markdown.read_text(encoding="utf-8")
            self.assertIn("![capture.png]", markdown_text)

            docx = root / "conversation.docx"
            export_docx(markdown, docx, document_title="Discord test", overwrite=True)
            with zipfile.ZipFile(docx) as archive:
                media = [name for name in archive.namelist() if name.startswith("word/media/")]
            self.assertEqual(len(media), 1)

    def test_existing_download_is_reused_without_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = download_conversation_assets(
                conversation(),
                root,
                fetch_bytes=lambda _url: PNG_1X1,
            )
            self.assertEqual(first.downloaded, 1)

            def fail_fetch(_url: str) -> bytes:
                raise AssertionError("existing asset should not be fetched again")

            second = download_conversation_assets(
                conversation(),
                root,
                fetch_bytes=fail_fetch,
            )
            self.assertEqual(second.downloaded, 0)
            self.assertEqual(second.reused, 1)
            self.assertEqual(second.available, 1)

    def test_download_failure_keeps_remote_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = download_conversation_assets(
                conversation(),
                Path(temporary),
                fetch_bytes=lambda _url: (_ for _ in ()).throw(OSError("network down")),
            )
            self.assertEqual(result.available, 0)
            self.assertEqual(len(result.failed), 1)

            localized = conversation_with_local_assets(
                conversation(),
                result.source_paths,
                relative_to=temporary,
            )
            self.assertTrue(localized.messages[0].assets[0].source_ref.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
