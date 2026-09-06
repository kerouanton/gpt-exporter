"""Build normalized conversation turns from classified legacy DOCX blocks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .model import LegacyBlock, LegacyRole


TURN_SCHEMA = "gpt-exporter-legacy-turns-v2"
TURN_BUILDER_VERSION = "legacy-turn-builder-v2"
TurnConfidence = Literal["high", "medium", "low", "none"]

_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True, slots=True)
class LegacyTurn:
    """One contiguous reconstructed conversation turn with Word provenance."""

    index: int
    role: LegacyRole
    confidence: TurnConfidence
    content: str
    block_count: int
    first_order: int
    last_order: int
    source_orders: tuple[int, ...]
    block_kinds: tuple[str, ...]
    tables: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["source_orders"] = list(self.source_orders)
        result["block_kinds"] = list(self.block_kinds)
        result["tables"] = [dict(table) for table in self.tables]
        return result


def _confidence(blocks: list[LegacyBlock]) -> TurnConfidence:
    best = "none"
    for block in blocks:
        candidate = block.role_confidence
        if _CONFIDENCE_RANK.get(candidate, 0) > _CONFIDENCE_RANK[best]:
            best = candidate
    return best  # type: ignore[return-value]


def _render_block(block: LegacyBlock) -> str:
    return block.text.strip()


def _turn(index: int, role: LegacyRole, blocks: list[LegacyBlock]) -> LegacyTurn:
    rendered = [_render_block(block) for block in blocks]
    content = "\n\n".join(part for part in rendered if part)
    tables = tuple(
        {
            "order": block.order,
            "rows": [list(row) for row in block.table_rows],
        }
        for block in blocks
        if block.kind == "table" and block.table_rows
    )
    return LegacyTurn(
        index=index,
        role=role,
        confidence=_confidence(blocks),
        content=content,
        block_count=len(blocks),
        first_order=blocks[0].order,
        last_order=blocks[-1].order,
        source_orders=tuple(block.order for block in blocks),
        block_kinds=tuple(block.kind for block in blocks),
        tables=tables,
    )


def build_turns(blocks: tuple[LegacyBlock, ...]) -> tuple[LegacyTurn, ...]:
    turns: list[LegacyTurn] = []
    current_role: LegacyRole | None = None
    current_blocks: list[LegacyBlock] = []

    def flush() -> None:
        nonlocal current_role, current_blocks
        if current_role is None or not current_blocks:
            return
        turns.append(_turn(len(turns), current_role, current_blocks))
        current_role = None
        current_blocks = []

    for block in blocks:
        if block.kind == "hyperlink_sentinel":
            continue
        if current_role is None:
            current_role = block.role
            current_blocks = [block]
            continue
        if block.role == current_role:
            current_blocks.append(block)
            continue
        flush()
        current_role = block.role
        current_blocks = [block]

    flush()
    return tuple(turns)
