"""Cumulative Discord DM history merge helpers.

The browser collector returns a snapshot of messages currently visible on
Discord.  The archive is intentionally historical: once a message has been
captured it remains in the canonical archive even if it later disappears from
Discord.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

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
    - archived IDs missing from the new snapshot are retained and marked deleted;
    - a previously deleted message that reappears has its deletion marker cleared.
    """
    if existing is None:
        return incoming, True
    if existing.conversation_id != incoming.conversation_id:
        raise ValueError("Cannot merge Discord histories from different conversations")

    observed_at = detected_at or _detected_at()
    incoming_by_id = {message.message_id: message for message in incoming.messages}
    existing_by_id = {message.message_id: message for message in existing.messages}

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
    merged_conversation = replace(
        incoming,
        messages=tuple(merged_messages),
        created_at=created_at,
        updated_at=updated_at,
    )

    if existing.title != merged_conversation.title:
        changed = True

    return merged_conversation, changed


__all__ = ["merge_dm_history"]
