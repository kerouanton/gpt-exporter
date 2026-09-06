"""Render immutable legacy Word body blocks as structure-preserving Markdown."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


_HEADING_RE = re.compile(r"^(?:heading|titre)\s*(\d+)$", re.IGNORECASE)


def _escape_inline(text: str) -> str:
    """Escape Markdown delimiters without changing visible text."""
    return (
        text.replace("\\", "\\\\")
        .replace("*", "\\*")
        .replace("_", "\\_")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def _style_flag(style, attribute: str) -> bool | None:
    """Resolve a font boolean through a Word style's base-style chain."""
    visited: set[int] = set()
    current = style
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        try:
            value = getattr(current.font, attribute)
        except (AttributeError, KeyError):
            value = None
        if value is not None:
            return bool(value)
        try:
            current = current.base_style
        except (AttributeError, KeyError):
            current = None
    return None


def _effective_run_flag(run, attribute: str) -> bool:
    """Resolve direct formatting plus inherited character-style formatting.

    Paragraph-style emphasis is intentionally not emitted as inline Markdown.
    Structural paragraph semantics such as headings are represented by their
    Markdown block syntax and rendered by the standard exporter style system.
    Duplicating that emphasis around every run can create adjacent CommonMark
    delimiters and changes representation without adding information.
    """
    direct = getattr(run, attribute)
    if direct is not None:
        return bool(direct)

    try:
        character_style = run.style
    except (AttributeError, KeyError):
        character_style = None
    character_value = _style_flag(character_style, attribute)
    return bool(character_value) if character_value is not None else False


def _run_markdown(run) -> str:
    text = str(run.text or "")
    if not text:
        return ""

    # CommonMark emphasis delimiters cannot reliably open/close next to
    # whitespace. Word often splits one emphasized span into runs that carry a
    # leading or trailing space, so keep that whitespace outside the Markdown
    # markers while preserving the visible text exactly.
    leading_match = re.match(r"^\s*", text)
    trailing_match = re.search(r"\s*$", text)
    leading = leading_match.group(0) if leading_match else ""
    trailing = trailing_match.group(0) if trailing_match else ""
    start = len(leading)
    end = len(text) - len(trailing) if trailing else len(text)
    core = text[start:end]

    if not core:
        return _escape_inline(text)

    core = _escape_inline(core)
    bold = _effective_run_flag(run, "bold")
    italic = _effective_run_flag(run, "italic")
    if bold and italic:
        core = f"***{core}***"
    elif bold:
        core = f"**{core}**"
    elif italic:
        core = f"*{core}*"

    return f"{leading}{core}{trailing}"


def _paragraph_inline_markdown(paragraph) -> str:
    """Preserve run emphasis, hyperlinks and meaningful manual Word line breaks."""
    parts: list[str] = []
    runs_by_xml = {id(run._r): run for run in paragraph.runs}
    for child in paragraph._p:
        local = child.tag.rsplit("}", 1)[-1]
        if local == "r":
            run = runs_by_xml.get(id(child))
            if run is not None:
                value = _run_markdown(run)
                if value:
                    parts.append(value)
            continue
        if local == "hyperlink":
            rid = child.get(qn("r:id"))
            label = "".join(child.itertext()).strip()
            target = ""
            if rid:
                relationship = paragraph.part.rels.get(rid)
                if relationship is not None:
                    target = str(getattr(relationship, "target_ref", "") or "")
            if label and target:
                parts.append(f"[{_escape_inline(label)}]({target})")
            elif label:
                parts.append(_escape_inline(label))
    text = "".join(parts)
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "  \n").strip()


def _style_name(paragraph) -> str:
    try:
        return str(paragraph.style.name or "").strip()
    except (AttributeError, KeyError):
        return ""


def _heading_level(paragraph) -> int | None:
    match = _HEADING_RE.match(_style_name(paragraph))
    if not match:
        return None
    return max(1, min(int(match.group(1)), 6))


def _children_by_tag(element, tag: str):
    """Find direct OOXML children using fully-qualified names, not XPath prefixes."""
    qualified = qn(tag)
    return [child for child in element if child.tag == qualified]


def _numbering_kind(document: Document, paragraph) -> tuple[str, int] | None:
    """Resolve paragraph numbering, including style-based Word lists."""
    p_pr = paragraph._p.pPr
    if p_pr is None or p_pr.numPr is None:
        style = _style_name(paragraph).casefold()
        if "list bullet" in style or "liste à puces" in style:
            return ("bullet", 0)
        if "list number" in style or "liste num" in style:
            return ("ordered", 0)
        return None

    num_pr = p_pr.numPr
    num_id = num_pr.numId
    ilvl = num_pr.ilvl
    if num_id is None:
        return None
    try:
        num_id_value = int(num_id.val)
    except (TypeError, ValueError):
        return None
    try:
        level = int(ilvl.val) if ilvl is not None else 0
    except (TypeError, ValueError):
        level = 0

    numbering = document.part.numbering_part.element
    nums = [
        node for node in _children_by_tag(numbering, "w:num")
        if node.get(qn("w:numId")) == str(num_id_value)
    ]
    if not nums:
        return ("ordered", level)

    abstract_id_nodes = _children_by_tag(nums[0], "w:abstractNumId")
    if not abstract_id_nodes:
        return ("ordered", level)
    abstract_id = abstract_id_nodes[0].get(qn("w:val"))

    abstracts = [
        node for node in _children_by_tag(numbering, "w:abstractNum")
        if node.get(qn("w:abstractNumId")) == abstract_id
    ]
    if not abstracts:
        return ("ordered", level)

    levels = [
        node for node in _children_by_tag(abstracts[0], "w:lvl")
        if node.get(qn("w:ilvl")) == str(level)
    ]
    if not levels:
        levels = [
            node for node in _children_by_tag(abstracts[0], "w:lvl")
            if node.get(qn("w:ilvl")) == "0"
        ]
    if not levels:
        return ("ordered", level)

    formats = _children_by_tag(levels[0], "w:numFmt")
    num_format = formats[0].get(qn("w:val")) if formats else "decimal"
    return ("bullet" if num_format == "bullet" else "ordered", level)


def _table_cell_markdown(cell) -> str:
    """Preserve inline Markdown semantics inside a Word table cell."""
    paragraphs: list[str] = []
    for paragraph in cell.paragraphs:
        value = _paragraph_inline_markdown(paragraph)
        if value:
            # Pipes delimit Markdown table cells. Hard line breaks cannot span a
            # physical Markdown table row, so use the same <br> convention as
            # ordinary ChatGPT Markdown exports for meaningful intra-cell lines.
            value = value.replace("|", "\\|").replace("  \n", "<br>")
            paragraphs.append(value)
    return "<br>".join(paragraphs).strip()


def _table_markdown(table) -> str:
    rows = [
        [_table_cell_markdown(cell) for cell in row.cells]
        for row in table.rows
        if any(str(cell.text).strip() for cell in row.cells)
    ]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def source_block_markdown(source_docx: Path) -> dict[int, str]:
    """Return body blocks preserving semantic formatting while normalizing layout."""
    document = Document(source_docx)
    result: dict[int, str] = {}
    for order, item in enumerate(document.iter_inner_content()):
        if hasattr(item, "rows"):
            text = _table_markdown(item)
        else:
            body = _paragraph_inline_markdown(item)
            if not body:
                continue
            heading = _heading_level(item)
            if heading is not None:
                text = f"{'#' * heading} {body}"
            else:
                numbering = _numbering_kind(document, item)
                if numbering is not None:
                    kind, level = numbering
                    indent = "  " * max(0, level)
                    marker = "-" if kind == "bullet" else "1."
                    text = f"{indent}{marker} {body}"
                else:
                    text = body
        if text:
            result[order] = text
    return result
