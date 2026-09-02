import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path

from gpt_exporter.model import (
    Attachment,
    ContentBlock,
    Conversation,
    Message,
    MessageReference,
    Participant,
    Reaction,
)


class NormalizedModelTests(unittest.TestCase):
    def test_conversation_represents_common_chat_features(self) -> None:
        created = datetime(2026, 8, 31, 8, 30, tzinfo=timezone.utc)
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conversation-1",
            title="Synthetic conversation",
            created_at=created,
            participants=(
                Participant("user-1", display_name="User", role="user"),
                Participant("bot-1", display_name="Assistant", role="assistant"),
            ),
            messages=(
                Message(
                    message_id="message-1",
                    author_id="user-1",
                    author_name="User",
                    author_role="user",
                    created_at=created,
                    text="Hello",
                    content=(ContentBlock(kind="text", text="Hello"),),
                    attachments=(
                        Attachment(
                            attachment_id="attachment-1",
                            filename="example.txt",
                            media_type="text/plain",
                            local_path=Path("assets/example.txt"),
                        ),
                    ),
                    reactions=(Reaction(value="👍", count=2),),
                    references=(
                        MessageReference(
                            kind="reply",
                            target_message_id="message-0",
                        ),
                    ),
                ),
            ),
            metadata={"native_type": "synthetic"},
        )

        self.assertEqual(conversation.provider_key, "synthetic")
        self.assertEqual(conversation.message_count, 1)
        self.assertEqual(conversation.messages[0].attachments[0].filename, "example.txt")
        self.assertEqual(conversation.messages[0].reactions[0].count, 2)
        self.assertEqual(
            conversation.messages[0].references[0].target_message_id,
            "message-0",
        )

    def test_normalized_records_are_immutable(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conversation-1",
        )

        with self.assertRaises(FrozenInstanceError):
            conversation.title = "changed"  # type: ignore[misc]

    def test_provider_metadata_has_no_required_schema(self) -> None:
        conversation = Conversation(
            provider_key="chatgpt",
            conversation_id="conversation-1",
            metadata={
                "chatgpt": {
                    "current_node": "node-1",
                    "model_slug": "example-model",
                }
            },
        )

        self.assertEqual(
            conversation.metadata["chatgpt"]["current_node"],
            "node-1",
        )


if __name__ == "__main__":
    unittest.main()
