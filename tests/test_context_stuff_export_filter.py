from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from export_provider_chatgpt.export.markdown import export_markdown


class ContextStuffExportFilterTests(unittest.TestCase):
    def _write_conversation(self, root: Path, tool_message: dict) -> Path:
        nodes = [
            (
                "user",
                {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["resume this"]},
                    "metadata": {},
                    "create_time": 1.0,
                },
            ),
            ("tool", tool_message),
            (
                "assistant",
                {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["visible answer"]},
                    "metadata": {},
                    "create_time": 3.0,
                },
            ),
        ]
        mapping = {}
        parent = None
        for node_id, message in nodes:
            mapping[node_id] = {
                "id": node_id,
                "parent": parent,
                "children": [],
                "message": message,
            }
            if parent is not None:
                mapping[parent]["children"].append(node_id)
            parent = node_id

        source = root / "conversation.json"
        source.write_text(
            json.dumps(
                {
                    "title": "Attachment context",
                    "conversation_id": "context-stuff-test",
                    "create_time": 1.0,
                    "update_time": 3.0,
                    "mapping": mapping,
                    "current_node": "assistant",
                }
            ),
            encoding="utf-8",
        )
        return source

    def test_context_stuff_with_embedded_image_is_not_exported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_conversation(
                root,
                {
                    "author": {"role": "tool", "name": "api_tool"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            "Make sure to include filecite instructions",
                            "<PARSED TEXT FOR PAGE: 1 / 2> secret document text",
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "sediment://file_00000000000000000000000000000000",
                            },
                        ],
                    },
                    "metadata": {
                        "command": "context_stuff",
                        "is_visually_hidden_from_conversation": False,
                    },
                    "create_time": 2.0,
                },
            )
            output = root / "conversation.md"

            result = export_markdown(source, output, resolve_assets=False)
            text = output.read_text(encoding="utf-8")

            self.assertEqual(result.exported_messages, 2)
            self.assertIn("resume this", text)
            self.assertIn("visible answer", text)
            self.assertNotIn("Make sure to include", text)
            self.assertNotIn("PARSED TEXT FOR PAGE", text)
            self.assertNotIn("secret document text", text)

    def test_real_generated_image_tool_is_still_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._write_conversation(
                root,
                {
                    "author": {"role": "tool", "name": "image_gen"},
                    "content": {
                        "content_type": "multimodal_text",
                        "parts": [
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "sediment://file_00000000000000000000000000000000",
                            }
                        ],
                    },
                    "metadata": {},
                    "create_time": 2.0,
                },
            )
            output = root / "conversation.md"

            result = export_markdown(source, output, resolve_assets=False)
            text = output.read_text(encoding="utf-8")

            self.assertEqual(result.exported_messages, 3)
            self.assertIn("Unavailable asset", text)
            self.assertIn("visible answer", text)


if __name__ == "__main__":
    unittest.main()
