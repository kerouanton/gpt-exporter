import json
import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path

from gpt_exporter.model import Conversation
from gpt_exporter.providers.chatgpt_normalizer import normalize_conversation_file


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "characterization"
    / "conversation_base.json"
)


class ChatGPTNormalizerTests(unittest.TestCase):
    def test_characterization_fixture_normalizes_to_common_model(self) -> None:
        conversation = normalize_conversation_file(FIXTURE)

        self.assertIsInstance(conversation, Conversation)
        self.assertEqual(conversation.provider_key, "chatgpt")
        self.assertEqual(conversation.conversation_id, "conv-characterization-001")
        self.assertEqual(conversation.title, "Characterization Fixture")
        self.assertEqual(conversation.message_count, 2)
        self.assertEqual(conversation.visible_message_count, 2)
        self.assertEqual(conversation.indexable_message_count, 2)
        self.assertEqual(
            [message.author_role for message in conversation.visible_messages],
            ["user", "assistant"],
        )
        self.assertEqual(
            [message.text for message in conversation.visible_messages],
            ["Base user message", "Base assistant reply"],
        )

    def test_normalizer_retains_chatgpt_native_provenance(self) -> None:
        conversation = normalize_conversation_file(FIXTURE)

        metadata = conversation.metadata["chatgpt"]
        self.assertEqual(metadata["current_node"], "node-assistant-1")
        self.assertEqual(metadata["all_nodes"], 3)
        self.assertEqual(metadata["active_nodes"], 3)
        self.assertTrue(str(metadata["source_path"]).endswith("conversation_base.json"))

        first = conversation.visible_messages[0]
        self.assertEqual(first.metadata["chatgpt"]["node_id"], "node-user-1")
        self.assertEqual(
            first.metadata["chatgpt"]["native_message"]["content"]["content_type"],
            "text",
        )

    def test_normalizer_exposes_legacy_origin_and_index_metadata_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "conversation.json"
            data = {
                "conversation_id": "conv-origin",
                "title": "Origin fixture",
                "current_node": "node-user",
                "gizmo_id": "g-custom",
                "gizmo_type": "custom",
                "conversation_template_id": "g-p-project",
                "conversation_origin": "native-origin",
                "default_model_slug": "gpt-test",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["node-user"],
                        "message": None,
                    },
                    "node-user": {
                        "id": "node-user",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "message-user",
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Hello"]},
                            "metadata": {
                                "nested": {"gizmo_id": "g-p-project"}
                            },
                        },
                    },
                },
            }
            path.write_text(json.dumps(data), encoding="utf-8")

            conversation = normalize_conversation_file(path)

        self.assertEqual(
            [(item.origin_id, item.origin_type) for item in conversation.origins],
            [
                ("g-p-project", "project"),
                ("g-custom", "custom_gpt"),
            ],
        )
        self.assertIn("top_level.conversation_template_id", conversation.origins[0].source)
        self.assertIn("message.metadata.nested.gizmo_id", conversation.origins[0].source)
        self.assertEqual(conversation.primary_origin.origin_id, "g-p-project")
        self.assertEqual(conversation.index_metadata["gizmo_id"], "g-custom")
        self.assertEqual(conversation.index_metadata["gizmo_type"], "custom")
        self.assertEqual(
            conversation.index_metadata["conversation_template_id"], "g-p-project"
        )
        self.assertEqual(conversation.index_metadata["conversation_origin"], "native-origin")
        self.assertEqual(conversation.index_metadata["default_model_slug"], "gpt-test")

    def test_display_and_search_projections_preserve_distinct_chatgpt_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "conversation.json"
            data = {
                "conversation_id": "conv-projections",
                "title": "Projection fixture",
                "current_node": "node-assistant",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["node-user", "node-branch"],
                        "message": None,
                    },
                    "node-user": {
                        "id": "node-user",
                        "parent": "root",
                        "children": ["node-assistant"],
                        "message": {
                            "id": "message-user",
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Visible user"]},
                            "metadata": {},
                        },
                    },
                    "node-branch": {
                        "id": "node-branch",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "message-branch",
                            "author": {"role": "user"},
                            "content": {"content_type": "text", "parts": ["Alternative branch"]},
                            "metadata": {},
                        },
                    },
                    "node-hidden": {
                        "id": "node-hidden",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "message-hidden",
                            "author": {"role": "assistant"},
                            "content": {"content_type": "text", "parts": ["Hidden"]},
                            "metadata": {"is_visually_hidden_from_conversation": True},
                        },
                    },
                    "node-context": {
                        "id": "node-context",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "message-context",
                            "author": {"role": "user"},
                            "content": {
                                "content_type": "user_editable_context",
                                "parts": ["Do not index"],
                            },
                            "metadata": {},
                        },
                    },
                    "node-assistant": {
                        "id": "node-assistant",
                        "parent": "node-user",
                        "children": [],
                        "message": {
                            "id": "message-assistant",
                            "author": {"role": "assistant"},
                            "content": {"content_type": "text", "parts": ["Visible assistant"]},
                            "metadata": {},
                        },
                    },
                },
            }
            path.write_text(json.dumps(data), encoding="utf-8")

            conversation = normalize_conversation_file(path)

        self.assertEqual(
            [message.message_id for message in conversation.visible_messages],
            ["message-user", "message-assistant"],
        )
        self.assertEqual(
            [message.message_id for message in conversation.indexable_messages],
            ["message-user", "message-branch", "message-assistant"],
        )
        self.assertEqual(conversation.visible_message_count, 2)
        self.assertEqual(conversation.indexable_message_count, 3)
        self.assertEqual(
            [message.search_text for message in conversation.indexable_messages],
            ["Visible user", "Alternative branch", "Visible assistant"],
        )
        self.assertNotIn(
            "message-hidden",
            [message.message_id for message in conversation.messages],
        )
        self.assertNotIn(
            "message-context",
            [message.message_id for message in conversation.messages],
        )


if __name__ == "__main__":
    unittest.main()
