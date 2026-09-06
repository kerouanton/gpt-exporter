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


def _run_markdown(run) -> str:
    text = str(run.text or "")
    if not text:
        return ""
    text = _escape_inline(text)
    if run.bold is True and run.italic is True:
        return f"***{text}***"
    if run.bold is True:
        return f"**{text}**"
    if run.italic is True:
        return f"*{text}*"
    return text


def _preserve_manual_breaks(text: str) -> str:
    """Convert Word manual breaks to Markdown hard breaks without losing edge breaks.

    CommonMark discards a hard break at the start/end of a paragraph because
    there is no visible inline content on one side.  Historical ChatGPT Word
    captures do contain such breaks.  A non-breaking space is used only as an
    invisible anchor when a break is otherwise at a paragraph edge.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\n" not in text:
        return text.strip()

    if text.startswith("\n"):
        text = "\u00a0" + text
    if text.endswith("\n"):
        text = text + "\u00a0"

    return text.replace("\n", "  \n").strip(" \t")


def _paragraph_inline_markdown(paragraph) -> str:
    """Preserve run emphasis, hyperlinks and manual Word line breaks."""
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
    return _preserve_manual_breaks("".join(parts))


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
    num_tag = qn("w:num")
    abstract_num_id_tag = qn("w:abstractNumId")
    abstract_num_tag = qn("w:abstractNum")
    level_tag = qn("w:lvl")
    num_format_tag = qn("w:numFmt")
    num_id_attr = qn("w:numId")
    abstract_num_id_attr = qn("w:abstractNumId")
    level_attr = qn("w:ilvl")
    value_attr = qn("w:val")

    nums = [node for node in numbering.findall(num_tag) if node.get(num_id_attr) == str(num_id_value)]
    if not nums:
        return ("ordered", level)
    abstract_id_nodes = nums[0].findall(abstract_num_id_tag)
    if not abstract_id_nodes:
        return ("ordered", level)
    abstract_id = abstract_id_nodes[0].get(value_attr)
    abstracts = [
        node
        for node in numbering.findall(abstract_num_tag)
        if node.get(abstract_num_id_attr) == str(abstract_id)
    ]
    if not abstracts:
        return ("ordered", level)
    levels = [
        node
        for node in abstracts[0].findall(level_tag)
        if node.get(level_attr) == str(level)
    ]
    if not levels:
        levels = [
            node
            for node in abstracts[0].findall(level_tag)
            if node.get(level_attr) == "0"
        ]
    if not levels:
        return ("ordered", level)
    formats = levels[0].findall(num_format_tag)
    num_format = formats[0].get(value_attr) if formats else "decimal"
    return ("bullet" if num_format == "bullet" else "ordered", level)


def _table_cell(value: str) -> str:
    return (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", "<br>")
        .strip()
    )


def _table_markdown(table) -> str:
    rows = [
        [_table_cell(cell.text) for cell in row.cells]
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
    """Return body blocks preserving headings, lists, emphasis, breaks and tables."""
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
