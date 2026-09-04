"""Conservative Phase-2 parser for historical ChatGPT DOCX copies."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

from .docx import CHATGPT_HYPERLINK_SENTINEL, _iso_datetime, _sha256, parse_legacy_filename
from .model import LEGACY_SCHEMA, LegacyBlock, LegacyConversation


PARSER_VERSION = "legacy-docx-parser-v1"

# These are deliberately weak language hints. They never assign a definitive
# role; they only help detect that a capture may begin inside an assistant turn.
ASSISTANT_OPENING_HINTS = re.compile(
    r"^(?:parfait|très bonne question|bonne idée|ton intuition|alors oui|oui[,. ]|exactement|en effet|tout à fait|tu as fait exactement)",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _iter_blocks(document):
    """Yield body paragraphs and tables in their original document order."""

    for order, item in enumerate(document.iter_inner_content()):
        if hasattr(item, "rows"):
            rows: list[str] = []
            for row in item.rows:
                cells = [_clean(cell.text) for cell in row.cells]
                rows.append(" | ".join(cells))
            text = "\n".join(row for row in rows if row.strip(" |"))
            yield LegacyBlock(order=order, kind="table", text=text)
            continue

        text = _clean(item.text)
        if not text:
            continue
        try:
            style = item.style.name or None
        except (AttributeError, KeyError):
            style = None
        if text == CHATGPT_HYPERLINK_SENTINEL:
            kind = "hyperlink_sentinel"
        elif style and (style.lower().startswith("heading") or style.lower().startswith("title")):
            kind = "heading"
        else:
            kind = "paragraph"
        yield LegacyBlock(order=order, kind=kind, text=text, style=style)


def _first_conversation_block(blocks: tuple[LegacyBlock, ...]) -> LegacyBlock | None:
    for block in blocks:
        if block.kind != "hyperlink_sentinel" and block.text:
            return block
    return None


def _classify_start(block: LegacyBlock | None) -> tuple[bool | None, str, list[str]]:
    if block is None:
        return None, "none", ["no visible conversation block found"]

    notes: list[str] = []
    text = block.text.strip()
    if ASSISTANT_OPENING_HINTS.search(text):
        notes.append("first visible block resembles an assistant continuation")
        return True, "medium", notes

    # A plain first block is not proof that the capture starts with a user turn.
    notes.append("first visible block role remains unresolved")
    return None, "low", notes


def parse_legacy_conversation(path: Path | str) -> LegacyConversation:
    """Build a versioned, read-only intermediate representation from DOCX."""

    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file: {source}")

    document = Document(source)
    filename = parse_legacy_filename(source)
    blocks = tuple(_iter_blocks(document))
    starts_mid, starts_confidence, notes = _classify_start(_first_conversation_block(blocks))
    properties = document.core_properties

    return LegacyConversation(
        schema=LEGACY_SCHEMA,
        source_type="legacy_docx",
        source_path=str(source),
        source_filename=source.name,
        source_sha256=_sha256(source),
        parser_version=PARSER_VERSION,
        category_hint=filename.category_hint,
        date_hint=filename.date_hint,
        title_hint=filename.title_hint,
        docx_created_at=_iso_datetime(properties.created),
        docx_modified_at=_iso_datetime(properties.modified),
        starts_mid_conversation=starts_mid,
        starts_mid_conversation_confidence=starts_confidence,
        blocks=blocks,
        notes=tuple(notes),
    )
