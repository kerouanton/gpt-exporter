"""Cumulative Discord DM history merge helpers.

The browser collector returns a snapshot of messages currently visible on
Discord.  The archive is intentionally historical: once a message has been
captured it remains in the canonical archive even if it later disappears from
Discord.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from gpt_exporter.core import CanonicalConversation, CanonicalMessage


def _detected_at() -> str:
    return datetime.now().astimezone().isoformat()


def _message_sort_key(message: CanonicalMessage) -> tuple[str, int, str]:
    timestamp = str(message.created_at or "")
    raw_id = str(message.message_id or "")
    try:
        numeric_id = int(raw_id)
    except ValueError:
        numeric_id = 0
    return timestamp, numeric_id, raw_id


def _message_bounds(conversation: CanonicalConversation) -> tuple[CanonicalMessage | None, CanonicalMessage | None]:
    if not conversation.messages:
        return None, None
    ordered = sorted(conversation.messages, key=_message_sort_key)
    return ordered[0], ordered[-1]


def _collector_history_complete(conversation: CanonicalConversation) -> bool:
    """Return only explicit collector evidence that the full DM was traversed.

    Older collector exports did not carry a trustworthy completeness signal.
    Treat those snapshots as incomplete for deletion inference rather than
    risking false tombstones when Discord supplied only a recent virtualized
    window.
    """
    diagnostics = conversation.metadata.get("diagnostics")
    return isinstance(diagnostics, dict) and diagnostics.get("history_complete") is True


def snapshot_covers_existing_history(
    existing: CanonicalConversation | None,
    incoming: CanonicalConversation,
) -> bool:
    """Return whether omissions in ``incoming`` are safe deletion evidence.

    Two independent conditions are required:
    1. the collector explicitly proved that it reached the complete DM history;
    2. the incoming message range spans the complete range already known locally.

    Range coverage alone is not sufficient: Discord's virtualized scroller can
    expose only a recent window while temporarily reporting scrollTop == 0.
    """
    if not _collector_history_complete(incoming):
        return False
    if existing is None or not existing.messages:
        return False
    old_first, old_last = _message_bounds(existing)
    new_first, new_last = _message_bounds(incoming)
    if old_first is None or old_last is None or new_first is None or new_last is None:
        return False
    return (
        _message_sort_key(new_first) <= _message_sort_key(old_first)
        and _message_sort_key(new_last) >= _message_sort_key(old_last)
    )


def _merge_present_message(
    existing: CanonicalMessage,
    incoming: CanonicalMessage,
    *,
    detected_at: str,
) -> tuple[CanonicalMessage, bool]:
    """Merge one message that is present in both snapshots."""
    metadata = dict(incoming.metadata)
    old_metadata = dict(existing.metadata)

    # A message that reappears was not actually deleted; a prior collector run
    # may simply have produced an incomplete snapshot.
    metadata.pop("deleted", None)
    metadata.pop("deleted_detected_at", None)

    content_changed = existing.content != incoming.content
    if content_changed:
        metadata["edited"] = True
        metadata.setdefault("edited_detected_at", detected_at)
    elif old_metadata.get("edited"):
        # Preserve historical knowledge that an edit was observed even if a
        # later collector payload no longer carries an explicit edited marker.
        metadata["edited"] = True
        if old_metadata.get("edited_detected_at"):
            metadata["edited_detected_at"] = old_metadata["edited_detected_at"]

    merged = replace(incoming, metadata=metadata)
    return merged, merged != existing


def merge_dm_history(
    existing: CanonicalConversation | None,
    incoming: CanonicalConversation,
    *,
    detected_at: str | None = None,
) -> tuple[CanonicalConversation, bool]:
    """Merge a newly captured DM snapshot into the cumulative archive.

    Rules are intentionally archive-oriented:
    - new message IDs are inserted;
    - present message IDs are refreshed and content changes are marked edited;
    - missing archived IDs are marked deleted only after explicit full-history
      collector evidence and complete coverage of the locally known range;
    - partial or legacy snapshots retain omitted archived messages unchanged;
    - a previously deleted message that reappears has its deletion marker cleared.
    """
    if existing is None:
        return incoming, True
    if existing.conversation_id != incoming.conversation_id:
        raise ValueError("Cannot merge Discord histories from different conversations")

    observed_at = detected_at or _detected_at()
    incoming_by_id = {message.message_id: message for message in incoming.messages}
    existing_by_id = {message.message_id: message for message in existing.messages}
    coverage_complete = snapshot_covers_existing_history(existing, incoming)
    collector_complete = _collector_history_complete(incoming)

    changed = False
    merged_messages: list[CanonicalMessage] = []

    for message_id, old_message in existing_by_id.items():
        new_message = incoming_by_id.get(message_id)
        if new_message is not None:
            merged, message_changed = _merge_present_message(
                old_message,
                new_message,
                detected_at=observed_at,
            )
            merged_messages.append(merged)
            changed = changed or message_changed
            continue

        if coverage_complete:
            metadata = dict(old_message.metadata)
            if not metadata.get("deleted"):
                metadata["deleted"] = True
                metadata["deleted_detected_at"] = observed_at
                old_message = replace(old_message, metadata=metadata)
                changed = True
        merged_messages.append(old_message)

    for message_id, new_message in incoming_by_id.items():
        if message_id not in existing_by_id:
            merged_messages.append(new_message)
            changed = True

    merged_messages.sort(key=_message_sort_key)

    # Keep the newest provider/conversation metadata while allowing the
    # cumulative message history to extend earlier than the current snapshot.
    created_at = merged_messages[0].created_at if merged_messages else incoming.created_at
    updated_at = merged_messages[-1].created_at if merged_messages else incoming.updated_at
    conversation_metadata = dict(incoming.metadata)
    if coverage_complete:
        coverage_label = "complete-verified"
    elif collector_complete:
        coverage_label = "complete-outside-known-range"
    else:
        coverage_label = "partial-or-unverified"
    conversation_metadata["snapshot_coverage"] = coverage_label
    merged_conversation = replace(
        incoming,
        messages=tuple(merged_messages),
        created_at=created_at,
        updated_at=updated_at,
        metadata=conversation_metadata,
    )

    if existing.title != merged_conversation.title:
        changed = True
    if dict(existing.metadata).get("snapshot_coverage") != coverage_label:
        changed = True

    return merged_conversation, changed


__all__ = ["merge_dm_history", "snapshot_covers_existing_history"]
