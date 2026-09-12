from __future__ import annotations

import unittest

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from export_provider_discord.history import (
    merge_dm_history,
    snapshot_covers_existing_history,
)


def conversation(
    *messages: CanonicalMessage,
    history_complete: bool | None = None,
) -> CanonicalConversation:
    metadata = {}
    if history_complete is not None:
        metadata["diagnostics"] = {"history_complete": history_complete}
    return CanonicalConversation(
        conversation_id="discord:123",
        provider_id="discord",
        title="@alice",
        messages=tuple(messages),
        metadata=metadata,
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
        self.assertEqual(merged.metadata["snapshot_coverage"], "partial-or-unverified")

    def test_range_coverage_without_collector_proof_does_not_tombstone(self) -> None:
        existing = conversation(message("1", "first"), message("2", "old text"), message("3", "still here"))
        incoming = conversation(message("1", "first"), message("3", "still here"))

        self.assertFalse(snapshot_covers_existing_history(existing, incoming))
        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T12:34:56+02:00")

        self.assertTrue(changed)
        middle = merged.messages[1]
        self.assertEqual(middle.message_id, "2")
        self.assertEqual(middle.content, "old text")
        self.assertFalse(middle.metadata.get("deleted", False))
        self.assertEqual(merged.metadata["snapshot_coverage"], "partial-or-unverified")

    def test_missing_archived_message_is_marked_deleted_only_after_verified_full_history(self) -> None:
        existing = conversation(message("1", "first"), message("2", "old text"), message("3", "still here"))
        incoming = conversation(
            message("1", "first"),
            message("3", "still here"),
            history_complete=True,
        )

        self.assertTrue(snapshot_covers_existing_history(existing, incoming))
        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T12:34:56+02:00")

        self.assertTrue(changed)
        middle = merged.messages[1]
        self.assertEqual(middle.message_id, "2")
        self.assertEqual(middle.content, "old text")
        self.assertTrue(middle.metadata["deleted"])
        self.assertEqual(middle.metadata["deleted_detected_at"], "2026-09-09T12:34:56+02:00")
        self.assertEqual(merged.metadata["snapshot_coverage"], "complete-verified")

    def test_partial_recent_snapshot_does_not_tombstone_older_archived_messages(self) -> None:
        existing = conversation(message("1", "old"), message("2", "middle"), message("3", "new"))
        incoming = conversation(message("3", "new"), history_complete=False)

        self.assertFalse(snapshot_covers_existing_history(existing, incoming))
        merged, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T12:34:56+02:00")

        self.assertTrue(changed)
        self.assertEqual([item.message_id for item in merged.messages], ["1", "2", "3"])
        self.assertFalse(any(item.metadata.get("deleted") for item in merged.messages))
        self.assertEqual(merged.metadata["snapshot_coverage"], "partial-or-unverified")

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

    def test_identical_verified_recapture_is_unchanged_after_coverage_metadata_exists(self) -> None:
        incoming = conversation(message("1", "same"), history_complete=True)
        existing = conversation(message("1", "same"), history_complete=True)
        first, changed = merge_dm_history(existing, incoming, detected_at="2026-09-09T15:00:00+02:00")
        self.assertTrue(changed)
        self.assertEqual(first.metadata["snapshot_coverage"], "complete-verified")

        second, changed_again = merge_dm_history(first, incoming, detected_at="2026-09-09T15:05:00+02:00")
        self.assertFalse(changed_again)
        self.assertEqual(second.messages, incoming.messages)


if __name__ == "__main__":
    unittest.main()
