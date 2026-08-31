import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.export.normalized import export_normalized_conversation
from gpt_exporter.model import Conversation, Message


class NormalizedExportTests(unittest.TestCase):
    def test_export_writes_markdown_from_common_model(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-1",
            title="Synthetic",
            messages=(Message(message_id="m1", author_name="Alice", text="Hello"),),
        )

        with tempfile.TemporaryDirectory() as temp_name:
            markdown = Path(temp_name) / "conversation.md"
            result = export_normalized_conversation(conversation, markdown)

            self.assertEqual(result.markdown_path, markdown.resolve())
            self.assertIsNone(result.docx_result)
            rendered = markdown.read_text(encoding="utf-8")
            self.assertIn("# Synthetic", rendered)
            self.assertIn("## Alice", rendered)
            self.assertIn("Hello", rendered)

    def test_export_can_delegate_docx_conversion(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-1",
            title="Synthetic",
        )

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            markdown = root / "conversation.md"
            docx = root / "conversation.docx"
            fake_result = mock.sentinel.docx_result

            with mock.patch(
                "gpt_exporter.export.normalized.export_docx",
                return_value=fake_result,
            ) as converter:
                result = export_normalized_conversation(
                    conversation,
                    markdown,
                    docx_path=docx,
                    overwrite=True,
                )

            converter.assert_called_once()
            args, kwargs = converter.call_args
            self.assertEqual(args[0], markdown.resolve())
            self.assertEqual(args[1], docx.resolve())
            self.assertEqual(kwargs["document_title"], "Synthetic")
            self.assertTrue(kwargs["overwrite"])
            self.assertIs(result.docx_result, fake_result)


if __name__ == "__main__":
    unittest.main()
