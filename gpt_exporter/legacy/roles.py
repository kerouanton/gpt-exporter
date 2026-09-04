"""Conservative role inference for legacy ChatGPT DOCX blocks.

Role inference is intentionally separated from DOCX parsing.  The raw v2 IR
keeps Word evidence unchanged; this module annotates a derived copy.

The real 42-document corpus showed that strong separators (two or more blank
Word body blocks) are useful anchors but far too sparse to represent every
conversation turn.  A classifier must therefore also react to one-blank
boundaries without treating every such boundary as a role change.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .model import LegacyBlock


ROLE_INFERENCE_VERSION = "legacy-role-inference-v2"

ASSISTANT_OPENING_HINTS = re.compile(
    r"^(?:parfait|excellent|très bonne question|bonne idée|ton intuition|"
    r"alors oui|oui[,.… ]|exactement|en effet|tout à fait|tu as fait exactement)",
    re.IGNORECASE,
)


def _plain_paragraph(block: LegacyBlock) -> bool:
    return (
        block.kind == "paragraph"
        and (block.style or "Normal") == "Normal"
        and block.left_indent_emu is None
        and block.right_indent_emu is None
        and block.first_line_indent_emu is None
        and block.shading_fill is None
        and not block.has_borders
        and not block.has_numbering
    )


def _assistant_anchor(block: LegacyBlock, *, strong: bool) -> tuple[str, str] | None:
    if not _plain_paragraph(block):
        return None

    assistant_like = bool(ASSISTANT_OPENING_HINTS.search(block.text.strip()))
    formatted = block.run_count >= 2 and block.bold_run_count >= 1

    # A one-blank boundary is common inside assistant formatting, so it only
    # becomes an Assistant anchor when lexical and Word-format evidence agree.
    if assistant_like and formatted:
        return "assistant", "high" if strong else "medium"

    # At a strong separator, preserved formatting alone is useful evidence but
    # is not strong enough to claim high confidence without an opening hint.
    if strong and formatted:
        return "assistant", "medium"

    return None


def _strong_user_anchor(block: LegacyBlock) -> tuple[str, str] | None:
    if not _plain_paragraph(block):
        return None
    if ASSISTANT_OPENING_HINTS.search(block.text.strip()):
        return None
    if (
        block.blank_blocks_before >= 2
        and block.run_count == 1
        and block.bold_run_count == 0
        and block.italic_run_count == 0
    ):
        return "user", "high"
    return None


def _first_anchor(block: LegacyBlock) -> tuple[str, str] | None:
    """Classify only unusually well-preserved first-turn signatures."""

    if not _plain_paragraph(block):
        return None

    assistant_like = bool(ASSISTANT_OPENING_HINTS.search(block.text.strip()))
    if block.blank_blocks_before >= 3:
        assistant = _assistant_anchor(block, strong=True)
        if assistant is not None:
            return assistant
        if block.bold_run_count == 0 and not assistant_like:
            return "user", "medium"
    return None


def _weak_user_sandwich(
    blocks: tuple[LegacyBlock, ...],
    index: int,
    *,
    current_role: str,
) -> bool:
    """Detect a short User turn between two Assistant regions.

    A plain single-run paragraph after one blank is not enough by itself: such
    paragraphs also occur inside Assistant answers.  It becomes useful User
    evidence when the preceding region is Assistant and the next non-sentinel
    block starts with a one-or-more-blank, independently recognizable
    Assistant anchor.  This models the common ``assistant -> user -> assistant``
    pattern without lexical classification of the User text.
    """

    if current_role != "assistant":
        return False
    block = blocks[index]
    if block.blank_blocks_before < 1 or not _plain_paragraph(block):
        return False
    if block.run_count != 1 or block.bold_run_count or block.italic_run_count:
        return False
    if ASSISTANT_OPENING_HINTS.search(block.text.strip()):
        return False

    for following in blocks[index + 1 :]:
        if following.kind == "hyperlink_sentinel":
            continue
        # The User turn may contain contiguous material, but a second blank
        # boundary without an Assistant anchor makes the sandwich ambiguous.
        if following.blank_blocks_before < 1:
            continue
        return _assistant_anchor(
            following,
            strong=following.blank_blocks_before >= 2,
        ) is not None
    return False


def infer_roles(blocks: tuple[LegacyBlock, ...]) -> tuple[LegacyBlock, ...]:
    """Annotate blocks while preferring ``unknown`` over long false propagation.

    Rules:
    - strong (>=2 blank) boundaries always start a fresh segment;
    - one-blank boundaries can start a clear Assistant anchor;
    - a weak User anchor is accepted only in an Assistant/User/Assistant
      structural sandwich;
    - when a User-labelled region reaches an ambiguous one-blank boundary, it
      stops propagating and becomes unknown instead of painting the rest of the
      document User;
    - Assistant regions may cross ordinary one-blank formatting boundaries
      unless contradictory role evidence appears.
    """

    if not blocks:
        return blocks

    result: list[LegacyBlock] = []
    current_role = "unknown"
    current_confidence = "none"
    first_conversation_block = True

    for index, block in enumerate(blocks):
        if block.kind == "hyperlink_sentinel":
            result.append(block)
            continue

        new_anchor: tuple[str, str] | None = None
        strong_boundary = block.blank_blocks_before >= 2
        weak_boundary = block.blank_blocks_before >= 1

        if first_conversation_block:
            new_anchor = _first_anchor(block)
            first_conversation_block = False
        elif strong_boundary:
            new_anchor = _assistant_anchor(block, strong=True) or _strong_user_anchor(block)
            if new_anchor is None:
                current_role, current_confidence = "unknown", "none"
        elif weak_boundary:
            new_anchor = _assistant_anchor(block, strong=False)
            if new_anchor is None and _weak_user_sandwich(
                blocks, index, current_role=current_role
            ):
                new_anchor = ("user", "medium")
            elif new_anchor is None and current_role == "user":
                # A User message rarely owns the following formatted answer.
                # Stop propagation at the first unresolved weak boundary.
                current_role, current_confidence = "unknown", "none"

        if new_anchor is not None:
            current_role, current_confidence = new_anchor

        if current_role == "unknown":
            result.append(replace(block, role="unknown", role_confidence="none"))
            continue

        is_anchor = new_anchor is not None
        confidence = current_confidence
        if not is_anchor:
            confidence = "medium" if current_confidence == "high" else "low"
        result.append(replace(block, role=current_role, role_confidence=confidence))

    return tuple(result)
