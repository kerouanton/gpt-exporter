from __future__ import annotations

import unittest

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from gpt_exporter.providers.discord.history import merge_dm_history


def conversation(*messages: CanonicalMessage) -> CanonicalConversation:
    return CanonicalConversation(
        conversation_id="discord:123",
        provider_id="discord",
        title="@alice",
        messages=tuple(messages),
    )


def message(message_id: str, content: str, *, deleted: bool = False) -> CanonicalMessage:
    metadata = {"provider": "discord"}
    if deleted:
        metadata.update({"deleted": True, "deleted_detected_at": "2026-09-09T10:00:00+02:00"})
    return CanonicalMessage(
        message_id=message_id,
        role="user",
        author_id="1",
        author_name="Bruno",
        content=content,
        created_at=f"2026-09-08T10:00:{int(message_id):02d}+00:00",
        metadata=metadata,
    )


class DiscordHistoryMergeTests(unittest.TestCase):
    def test_appends_new_messages_without_losing_existing_history(self) -> None:
        existing = conversation(message("1", "one"), message("2", "two"))
        incoming = conversation(message("1", "one"), message("2", "two"), message("3", "three"))

        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T12:00:00+02:00")

        self.assertTrue(changed)
        self.assertEqual([item.message_id for item in merged.messages], ["1", "2", "3"])
        self.assertFalse(any(item.metadata.get("deleted") for item in merged.messages))

    def test_missing_archived_message_is_retained_and_marked_deleted(self) -> None:
        existing = conversation(message("1", "old text"), message("2", "still here"))
        incoming = conversation(message("2", "still here"))

        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T12:34:56+02:00")

        self.assertTrue(changed)
        first = merged.messages[0]
        self.assertEqual(first.message_id, "1")
        self.assertEqual(first.content, "old text")
        self.assertTrue(first.metadata["deleted"])
        self.assertEqual(first.metadata["deleted_detected_at"], "2026-09-09T12:34:56+02:00")

    def test_deleted_message_that_reappears_clears_tombstone(self) -> None:
        existing = conversation(message("1", "one", deleted=True))
        incoming = conversation(message("1", "one"))

        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T13:00:00+02:00")

        self.assertTrue(changed)
        self.assertNotIn("deleted", merged.messages[0].metadata)
        self.assertNotIn("deleted_detected_at", merged.messages[0].metadata)

    def test_same_message_id_with_changed_content_is_marked_edited(self) -> None:
        existing = conversation(message("1", "old"))
        incoming = conversation(message("1", "new"))

        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T14:00:00+02:00")

        self.assertTrue(changed)
        self.assertEqual(merged.messages[0].content, "new")
        self.assertTrue(merged.messages[0].metadata["edited"])
        self.assertEqual(merged.messages[0].metadata["edited_detected_at"], "2026-09-09T14:00:00+02:00")

    def test_identical_recapture_is_unchanged(self) -> None:
        existing = conversation(message("1", "same"))
        incoming = conversation(message("1", "same"))

        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T15:00:00+02:00")

        self.assertFalse(changed)
        self.assertEqual(merged.messages, incoming.messages)


if __name__ == "__main__":
    unittest.main()
