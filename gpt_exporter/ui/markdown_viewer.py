"""Small dependency-light Markdown viewer built on Tkinter and markdown-it-py."""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Iterable
import webbrowser

from markdown_it import MarkdownIt


@dataclass(frozen=True, slots=True)
class MarkdownSegment:
    """One rendered text segment with semantic tags and an optional link target."""

    text: str
    tags: tuple[str, ...] = ()
    href: str | None = None


def _append_segment(
    output: list[MarkdownSegment],
    text: str,
    tags: Iterable[str] = (),
    href: str | None = None,
) -> None:
    if not text:
        return
    normalized_tags = tuple(tags)
    if output and output[-1].tags == normalized_tags and output[-1].href == href:
        previous = output[-1]
        output[-1] = MarkdownSegment(previous.text + text, normalized_tags, href)
        return
    output.append(MarkdownSegment(text, normalized_tags, href))


def _inline_segments(token, block_tags: tuple[str, ...]) -> list[MarkdownSegment]:
    output: list[MarkdownSegment] = []
    inline_tags: list[str] = []
    href: str | None = None

    for child in token.children or ():
        kind = child.type
        if kind == "text":
            _append_segment(output, child.content, (*block_tags, *inline_tags), href)
        elif kind in {"softbreak", "hardbreak"}:
            _append_segment(output, "\n", (*block_tags, *inline_tags), href)
        elif kind == "strong_open":
            inline_tags.append("strong")
        elif kind == "strong_close":
            if "strong" in inline_tags:
                inline_tags.remove("strong")
        elif kind == "em_open":
            inline_tags.append("emphasis")
        elif kind == "em_close":
            if "emphasis" in inline_tags:
                inline_tags.remove("emphasis")
        elif kind == "code_inline":
            _append_segment(output, child.content, (*block_tags, *inline_tags, "code"), href)
        elif kind == "link_open":
            href = child.attrGet("href")
            inline_tags.append("link")
        elif kind == "link_close":
            if "link" in inline_tags:
                inline_tags.remove("link")
            href = None
        elif kind == "image":
            label = child.content or child.attrGet("alt") or "image"
            target = child.attrGet("src")
            _append_segment(output, f"[{label}]", (*block_tags, "link"), target)
        elif kind == "html_inline":
            _append_segment(output, child.content, (*block_tags, *inline_tags), href)

    return output


def markdown_segments(source: str) -> tuple[MarkdownSegment, ...]:
    """Convert Markdown to a small semantic render model suitable for Tkinter."""

    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    tokens = parser.parse(source)
    output: list[MarkdownSegment] = []
    block_tags: list[str] = []
    list_stack: list[dict[str, int | str]] = []

    for token in tokens:
        kind = token.type

        if kind == "heading_open":
            level = token.tag.removeprefix("h")
            block_tags = [f"heading{level}"]
        elif kind == "heading_close":
            _append_segment(output, "\n\n")
            block_tags = []
        elif kind == "paragraph_open":
            if not block_tags:
                block_tags = ["paragraph"]
        elif kind == "paragraph_close":
            _append_segment(output, "\n\n")
            block_tags = [tag for tag in block_tags if tag == "quote"]
        elif kind == "blockquote_open":
            block_tags.append("quote")
        elif kind == "blockquote_close":
            block_tags = [tag for tag in block_tags if tag != "quote"]
            _append_segment(output, "\n")
        elif kind == "bullet_list_open":
            list_stack.append({"kind": "bullet", "next": 1})
        elif kind == "ordered_list_open":
            start_value = token.attrGet("start")
            try:
                start = int(start_value) if start_value is not None else 1
            except ValueError:
                start = 1
            list_stack.append({"kind": "ordered", "next": start})
        elif kind in {"bullet_list_close", "ordered_list_close"}:
            if list_stack:
                list_stack.pop()
            _append_segment(output, "\n")
        elif kind == "list_item_open":
            if list_stack:
                state = list_stack[-1]
                if state["kind"] == "ordered":
                    number = int(state["next"])
                    prefix = f"{number}. "
                    state["next"] = number + 1
                else:
                    prefix = "• "
                _append_segment(output, prefix, ("list_prefix",))
        elif kind == "list_item_close":
            _append_segment(output, "\n")
        elif kind == "inline":
            for segment in _inline_segments(token, tuple(block_tags)):
                _append_segment(output, segment.text, segment.tags, segment.href)
        elif kind in {"fence", "code_block"}:
            _append_segment(output, token.content.rstrip("\n"), ("code_block",))
            _append_segment(output, "\n\n")
        elif kind == "hr":
            _append_segment(output, "────────────────────────\n\n", ("rule",))

    while output and not output[-1].text.strip():
        output.pop()
    return tuple(output)


class MarkdownViewer(tk.Toplevel):
    """Scrollable read-only viewer for Markdown documentation."""

    def __init__(self, parent: tk.Misc, *, title: str, markdown: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("900x700")
        self.minsize(640, 420)
        self.transient(parent)

        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)

        self.text = ScrolledText(container, wrap="word", undo=False, padx=12, pady=12)
        self.text.pack(fill="both", expand=True)

        button_row = ttk.Frame(container)
        button_row.pack(fill="x", pady=(8, 0))
        ttk.Button(button_row, text="Close", command=self.destroy).pack(side="right")

        self._configure_tags()
        self._insert_markdown(markdown)
        self.text.configure(state="disabled")
        self.bind("<Escape>", lambda _event: self.destroy())

    def _configure_tags(self) -> None:
        default_font = tkfont.nametofont("TkDefaultFont")
        fixed_font = tkfont.nametofont("TkFixedFont")

        for level, increment in ((1, 6), (2, 4), (3, 2), (4, 1), (5, 0), (6, 0)):
            heading_font = default_font.copy()
            heading_font.configure(size=max(8, default_font.cget("size") + increment), weight="bold")
            self.text.tag_configure(f"heading{level}", font=heading_font, spacing1=8, spacing3=4)

        strong_font = default_font.copy()
        strong_font.configure(weight="bold")
        emphasis_font = default_font.copy()
        emphasis_font.configure(slant="italic")

        self.text.tag_configure("strong", font=strong_font)
        self.text.tag_configure("emphasis", font=emphasis_font)
        self.text.tag_configure("code", font=fixed_font)
        self.text.tag_configure("code_block", font=fixed_font, lmargin1=20, lmargin2=20, spacing1=6, spacing3=6)
        self.text.tag_configure("quote", lmargin1=24, lmargin2=24)
        self.text.tag_configure("list_prefix", lmargin1=16)
        self.text.tag_configure("link", underline=True)

    def _insert_markdown(self, markdown: str) -> None:
        link_number = 0
        for segment in markdown_segments(markdown):
            tags = list(segment.tags)
            if segment.href:
                link_tag = f"href_{link_number}"
                link_number += 1
                self.text.tag_configure(link_tag, underline=True)
                self.text.tag_bind(
                    link_tag,
                    "<Button-1>",
                    lambda _event, url=segment.href: webbrowser.open(url),
                )
                self.text.tag_bind(link_tag, "<Enter>", lambda _event: self.text.configure(cursor="hand2"))
                self.text.tag_bind(link_tag, "<Leave>", lambda _event: self.text.configure(cursor=""))
                tags.append(link_tag)
            self.text.insert("end", segment.text, tuple(tags))

        self.text.see("1.0")


def show_markdown_document(parent: tk.Misc, *, title: str, markdown: str) -> MarkdownViewer:
    """Open one Markdown document in a modeless viewer window."""

    return MarkdownViewer(parent, title=title, markdown=markdown)


__all__ = ["MarkdownSegment", "MarkdownViewer", "markdown_segments", "show_markdown_document"]
