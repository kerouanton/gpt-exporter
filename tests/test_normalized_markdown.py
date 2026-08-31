import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest
from datetime import datetime, timezone

from gpt_exporter.export.normalized_markdown import render_conversation_markdown
from gpt_exporter.model import Conversation, Message


class NormalizedMarkdownTests(unittest.TestCase):
    def test_renderer_uses_only_normalized_model(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-1",
            title="Synthetic conversation",
            created_at=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 31, 8, 1, tzinfo=timezone.utc),
            messages=(
                Message(
                    message_id="m1",
                    author_name="Alice",
                    author_role="user",
                    created_at=datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc),
                    text="Hello",
                ),
                Message(
                    message_id="m2",
                    author_name="Bob",
                    author_role="assistant",
                    created_at=datetime(2026, 8, 31, 8, 1, tzinfo=timezone.utc),
                    text="Hi Alice",
                ),
            ),
        )

        rendered = render_conversation_markdown(conversation, include_timestamps=True)

        self.assertIn("# Synthetic conversation", rendered)
        self.assertNotIn("- Provider:", rendered)
        self.assertIn("- Conversation ID: `conv-1`", rendered)
        self.assertIn("## Alice", rendered)
        self.assertIn("Hello", rendered)
        self.assertIn("## Bob", rendered)
        self.assertIn("Hi Alice", rendered)
        self.assertIn("2026-08-31T08:00:00+00:00", rendered)

    def test_renderer_uses_visible_projection_and_display_order(self) -> None:
        conversation = Conversation(
            provider_key="synthetic",
            conversation_id="conv-projection",
            messages=(
                Message(
                    message_id="search-only",
                    author_name="Hidden branch",
                    text="Do not render",
                    is_visible=False,
                    is_indexable=True,
                    search_order=1,
                ),
                Message(
                    message_id="second",
                    author_name="Second",
                    text="Second visible",
                    display_order=2,
                ),
                Message(
                    message_id="first",
                    author_name="First",
                    text="First visible",
                    display_order=1,
                ),
            ),
        )

        rendered = render_conversation_markdown(conversation)

        self.assertIn("- Messages: 2", rendered)
        self.assertNotIn("Do not render", rendered)
        self.assertLess(rendered.index("First visible"), rendered.index("Second visible"))

    def test_renderer_does_not_invent_provider_specific_author_names(self) -> None:
        conversation = Conversation(
            provider_key="chatgpt",
            conversation_id="conv-1",
            messages=(
                Message(message_id="m1", author_role="user", text="Question"),
                Message(message_id="m2", author_role="assistant", text="Answer"),
            ),
        )

        rendered = render_conversation_markdown(conversation)

        self.assertIn("## User", rendered)
        self.assertIn("## Assistant", rendered)
        self.assertNotIn("## Bruno", rendered)
        self.assertNotIn("## ChatGPT", rendered)


if __name__ == "__main__":
    unittest.main()
