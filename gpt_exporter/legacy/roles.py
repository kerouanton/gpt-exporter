"""Conservative role inference for legacy ChatGPT DOCX blocks.

The inference deliberately works on structural segment starts instead of trying
 to classify every paragraph lexically.  A segment begins after a strong Word
separator (two or more omitted/blank body blocks).  Only signatures validated
against the real 42-document corpus become role anchors; ambiguous segments
remain ``unknown``.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .model import LegacyBlock


ROLE_INFERENCE_VERSION = "legacy-role-inference-v1"

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


def _segment_anchor(block: LegacyBlock, *, first_segment: bool) -> tuple[str, str] | None:
    """Return a conservative role/confidence anchor for one segment start."""

    if not _plain_paragraph(block):
        return None

    text = block.text.strip()
    assistant_like = bool(ASSISTANT_OPENING_HINTS.search(text))

    # Corpus evidence: assistant responses beginning after a strong separator
    # commonly contain multiple runs with at least one bold run.  Lexical
    # opening hints strengthen this but are not used alone for internal turns.
    if block.blank_blocks_before >= 2 and block.bold_run_count >= 1 and block.run_count >= 2:
        return "assistant", "high" if assistant_like else "medium"

    # Corpus evidence: internal User turns after strong separators are often a
    # single plain run with no bold/italic formatting.
    if (
        block.blank_blocks_before >= 2
        and block.run_count == 1
        and block.bold_run_count == 0
        and block.italic_run_count == 0
        and not assistant_like
    ):
        return "user", "high"

    # The first preserved turn often has three blank body blocks before it and
    # can contain several plain runs because of the copied page wrapper.  On
    # the real corpus this is a useful User anchor only when no assistant-like
    # opening or bold evidence is present.
    if (
        first_segment
        and block.blank_blocks_before >= 3
        and block.bold_run_count == 0
        and not assistant_like
    ):
        return "user", "medium"

    # A captured conversation may begin in the middle of an Assistant answer.
    # At the first segment only, the combination of an assistant-like opening
    # and preserved formatting is enough for a medium-confidence anchor.
    if first_segment and block.blank_blocks_before >= 3 and assistant_like:
        return "assistant", "medium"

    return None


def infer_roles(blocks: tuple[LegacyBlock, ...]) -> tuple[LegacyBlock, ...]:
    """Assign roles to structurally anchored segments; keep all others unknown.

    A new segment starts at the first conversation block and whenever a block
    has ``blank_blocks_before >= 2``.  Role evidence is evaluated only at the
    segment start, then propagated inside that segment.  Crucially, an
    ambiguous strong boundary starts a fresh ``unknown`` segment instead of
    inheriting the previous role.
    """

    if not blocks:
        return blocks

    result: list[LegacyBlock] = []
    current_role = "unknown"
    current_confidence = "none"
    first_conversation_segment = True

    for block in blocks:
        if block.kind == "hyperlink_sentinel":
            result.append(block)
            continue

        new_segment = first_conversation_segment or block.blank_blocks_before >= 2
        if new_segment:
            anchor = _segment_anchor(block, first_segment=first_conversation_segment)
            if anchor is None:
                current_role, current_confidence = "unknown", "none"
            else:
                current_role, current_confidence = anchor
            first_conversation_segment = False

        if current_role == "unknown":
            result.append(replace(block, role="unknown", role_confidence="none"))
        else:
            # The start block carries the anchor confidence.  Following blocks
            # are structurally propagated and therefore one level weaker.
            confidence = current_confidence
            if not new_segment:
                confidence = "medium" if current_confidence == "high" else "low"
            result.append(
                replace(block, role=current_role, role_confidence=confidence)
            )

    return tuple(result)
