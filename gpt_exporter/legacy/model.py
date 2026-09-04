"""Versioned intermediate representation for legacy ChatGPT DOCX sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


LEGACY_SCHEMA = "gpt-exporter-legacy-conversation-v2"
LegacyRole = Literal["user", "assistant", "unknown"]
LegacyBlockKind = Literal["paragraph", "heading", "table", "hyperlink_sentinel"]


@dataclass(frozen=True, slots=True)
class LegacyBlock:
    """One ordered block recovered from a legacy Word document."""

    order: int
    kind: LegacyBlockKind
    text: str
    style: str | None = None
    role: LegacyRole = "unknown"
    role_confidence: str = "none"

    # Word evidence retained for later role/turn inference.  These fields are
    # observations only; none of them implies a role on its own.
    blank_blocks_before: int = 0
    alignment: str | None = None
    left_indent_emu: int | None = None
    right_indent_emu: int | None = None
    first_line_indent_emu: int | None = None
    shading_fill: str | None = None
    has_borders: bool = False
    has_numbering: bool = False
    run_count: int = 0
    bold_run_count: int = 0
    italic_run_count: int = 0
    hyperlink_count: int = 0


@dataclass(frozen=True, slots=True)
class LegacyConversation:
    """Loss-minimizing representation derived from one immutable DOCX source."""

    schema: str
    source_type: str
    source_path: str
    source_filename: str
    source_sha256: str
    parser_version: str
    category_hint: str | None
    date_hint: str | None
    title_hint: str
    docx_created_at: str | None
    docx_modified_at: str | None
    starts_mid_conversation: bool | None
    starts_mid_conversation_confidence: str
    blocks: tuple[LegacyBlock, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["blocks"] = [asdict(block) for block in self.blocks]
        result["notes"] = list(self.notes)
        return result
