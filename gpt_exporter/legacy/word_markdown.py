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
    nums = numbering.xpath(f"./w:num[@w:numId='{num_id_value}']")
    if not nums:
        return ("ordered", level)
    abstract_id_nodes = nums[0].xpath("./w:abstractNumId")
    if not abstract_id_nodes:
        return ("ordered", level)
    abstract_id = abstract_id_nodes[0].get(qn("w:val"))
    abstracts = numbering.xpath(f"./w:abstractNum[@w:abstractNumId='{abstract_id}']")
    if not abstracts:
        return ("ordered", level)
    levels = abstracts[0].xpath(f"./w:lvl[@w:ilvl='{level}']")
    if not levels:
        levels = abstracts[0].xpath("./w:lvl[@w:ilvl='0']")
    if not levels:
        return ("ordered", level)
    formats = levels[0].xpath("./w:numFmt")
    num_format = formats[0].get(qn("w:val")) if formats else "decimal"
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
