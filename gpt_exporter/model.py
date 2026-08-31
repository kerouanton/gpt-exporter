"""Provider-neutral conversation model used by exporter core layers.

Provider-native data remains preserved separately. These immutable records are a
normalized, rebuildable representation consumed by common indexing, browsing,
analysis, and derived-export layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


Metadata = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Participant:
    """One person, account, assistant, bot, or system actor in a conversation."""

    participant_id: str
    display_name: str = ""
    role: str = ""
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContentBlock:
    """One ordered block of message content."""

    kind: str
    text: str = ""
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Attachment:
    """One attachment associated with a normalized message."""

    attachment_id: str
    filename: str = ""
    media_type: str = ""
    local_path: Path | None = None
    source_url: str = ""
    size_bytes: int | None = None
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Reaction:
    """One reaction summary attached to a message."""

    value: str
    count: int = 1
    participant_ids: tuple[str, ...] = ()
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MessageReference:
    """A reply, quote, parent, branch, or other message relationship."""

    kind: str
    target_message_id: str = ""
    target_conversation_id: str = ""
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Message:
    """One normalized message with separate display and search projections."""

    message_id: str
    author_id: str = ""
    author_name: str = ""
    author_role: str = ""
    created_at: datetime | None = None
    edited_at: datetime | None = None
    text: str = ""
    search_text: str = ""
    is_visible: bool = True
    is_indexable: bool = True
    display_order: int | None = None
    search_order: int | None = None
    content: tuple[ContentBlock, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    reactions: tuple[Reaction, ...] = ()
    references: tuple[MessageReference, ...] = ()
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Conversation:
    """Provider-neutral conversation/thread representation."""

    provider_key: str
    conversation_id: str
    title: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    participants: tuple[Participant, ...] = ()
    messages: tuple[Message, ...] = ()
    metadata: Metadata = field(default_factory=dict)

    @property
    def message_count(self) -> int:
        """Return the number of normalized message records in the union model."""
        return len(self.messages)

    @property
    def visible_messages(self) -> tuple[Message, ...]:
        """Return display-visible messages in provider-defined display order."""
        visible = [message for message in self.messages if message.is_visible]
        return tuple(
            sorted(
                visible,
                key=lambda message: (
                    message.display_order is None,
                    message.display_order if message.display_order is not None else 0,
                ),
            )
        )

    @property
    def visible_message_count(self) -> int:
        return len(self.visible_messages)

    @property
    def indexable_messages(self) -> tuple[Message, ...]:
        """Return searchable messages in provider-defined search order."""
        indexable = [message for message in self.messages if message.is_indexable]
        return tuple(
            sorted(
                indexable,
                key=lambda message: (
                    message.search_order is None,
                    message.search_order if message.search_order is not None else 0,
                ),
            )
        )

    @property
    def indexable_message_count(self) -> int:
        return len(self.indexable_messages)


__all__ = [
    "Attachment",
    "ContentBlock",
    "Conversation",
    "Message",
    "MessageReference",
    "Metadata",
    "Participant",
    "Reaction",
]
