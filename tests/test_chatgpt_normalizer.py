import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

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
        self.assertEqual(
            [message.author_role for message in conversation.messages],
            ["user", "assistant"],
        )
        self.assertEqual(
            [message.text for message in conversation.messages],
            ["Base user message", "Base assistant reply"],
        )

    def test_normalizer_retains_chatgpt_native_provenance(self) -> None:
        conversation = normalize_conversation_file(FIXTURE)

        metadata = conversation.metadata["chatgpt"]
        self.assertEqual(metadata["current_node"], "node-assistant-1")
        self.assertEqual(metadata["all_nodes"], 3)
        self.assertEqual(metadata["active_nodes"], 3)
        self.assertTrue(str(metadata["source_path"]).endswith("conversation_base.json"))

        first = conversation.messages[0]
        self.assertEqual(first.metadata["chatgpt"]["node_id"], "node-user-1")
        self.assertEqual(
            first.metadata["chatgpt"]["native_message"]["content"]["content_type"],
            "text",
        )


if __name__ == "__main__":
    unittest.main()
