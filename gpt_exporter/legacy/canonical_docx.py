"""Generate normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gpt_exporter.export.docx import export_docx


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v1"


@dataclass(frozen=True, slots=True)
class CanonicalLegacyDocxResult:
    output_path: Path
    turn_count: int
    unknown_turn_count: int
    skipped: bool


def _markdown_escape_line(value: str) -> str:
    """Avoid accidental top-level Markdown syntax in metadata values."""
    return value.replace("\r", " ").replace("\n", " ").strip()


def build_legacy_markdown(conversation: dict[str, Any]) -> str:
    """Build a conservative Markdown document for one normalized legacy conversation.

    The DOCX exporter receives the conversation title separately through its
    ``document_title`` argument.  Do not emit a Markdown H1 here, otherwise the
    rendered DOCX contains the title twice.
    """
    source_filename = str(conversation.get("source_filename") or "unknown").strip()
    source_sha = str(conversation.get("source_sha256") or "unknown").strip()
    category = str(conversation.get("category_hint") or "").strip()
    date_hint = str(conversation.get("date_hint") or "").strip()
    parser_version = str(conversation.get("parser_version") or "unknown").strip()
    role_version = str(conversation.get("role_inference_version") or "unknown").strip()
    turn_version = str(conversation.get("turn_builder_version") or "unknown").strip()
    starts_mid = conversation.get("starts_mid_conversation")

    lines = [
        "> **Legacy DOCX normalized derivative.** This document was reconstructed from an immutable historical Word capture. The historical DOCX remains the authoritative source.",
        "",
        "## Provenance",
        "",
        f"- Source file: `{_markdown_escape_line(source_filename)}`",
        f"- Source SHA-256: `{_markdown_escape_line(source_sha)}`",
        f"- Parser: `{_markdown_escape_line(parser_version)}`",
        f"- Role inference: `{_markdown_escape_line(role_version)}`",
        f"- Turn builder: `{_markdown_escape_line(turn_version)}`",
        f"- Canonical DOCX renderer: `{CANONICAL_LEGACY_DOCX_VERSION}`",
    ]
    if category:
        lines.append(f"- Category hint: `{_markdown_escape_line(category)}`")
    if date_hint:
        lines.append(f"- Date hint: `{_markdown_escape_line(date_hint)}`")
    if starts_mid is True:
        lines.append("- Capture note: source probably starts in the middle of a conversation")
    elif starts_mid is False:
        lines.append("- Capture note: no mid-conversation start detected")
    else:
        lines.append("- Capture note: start position unresolved")

    turns = conversation.get("turns")
    if not isinstance(turns, list):
        raise ValueError(f"Invalid normalized turns for {source_filename}")

    unknown_count = sum(
        1
        for turn in turns
        if isinstance(turn, dict) and str(turn.get("role") or "unknown") == "unknown"
    )
    if unknown_count:
        lines.extend(
            [
                "",
                f"> **Reconstruction note:** {unknown_count} turn(s) remain `UNKNOWN` because the historical Word evidence was not strong enough to assign a role safely.",
            ]
        )

    lines.extend(["", "---", ""])

    role_titles = {"user": "User", "assistant": "Assistant", "unknown": "Unknown"}
    emitted = 0
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        body = str(turn.get("content") or "").strip()
        if not body:
            continue
        role = str(turn.get("role") or "unknown").strip().lower()
        heading = role_titles.get(role, "Unknown")
        confidence = str(turn.get("confidence") or "none").strip()
        first_order = turn.get("first_order")
        last_order = turn.get("last_order")

        lines.extend([f"## {heading}", ""])
        metadata = []
        if confidence and confidence != "none":
            metadata.append(f"confidence={confidence}")
        if first_order is not None and last_order is not None:
            metadata.append(f"source-order={first_order}..{last_order}")
        if metadata:
            lines.extend([f"*Legacy reconstruction metadata: {', '.join(metadata)}*", ""])
        lines.extend([body, ""])
        emitted += 1

    if not emitted:
        lines.extend(["## Unknown", "", "No reconstructed conversation turns were available.", ""])

    return "\n".join(lines).rstrip() + "\n"


def canonical_output_name(conversation: dict[str, Any]) -> str:
    source_filename = str(conversation.get("source_filename") or "legacy.docx")
    stem = Path(source_filename).stem
    return f"{stem} [normalized].docx"


def export_legacy_canonical_docx(
    conversation: dict[str, Any],
    output_dir: Path,
    *,
    overwrite: bool = False,
) -> CanonicalLegacyDocxResult:
    """Export one normalized derivative without touching the historical DOCX."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / canonical_output_name(conversation)

    turns = conversation.get("turns")
    if not isinstance(turns, list):
        raise ValueError("Legacy conversation has no normalized turns list")
    turn_count = sum(
        1 for turn in turns if isinstance(turn, dict) and str(turn.get("content") or "").strip()
    )
    unknown_count = sum(
        1
        for turn in turns
        if isinstance(turn, dict)
        and str(turn.get("content") or "").strip()
        and str(turn.get("role") or "unknown") == "unknown"
    )

    markdown = build_legacy_markdown(conversation)
    with tempfile.TemporaryDirectory(prefix="gpt-exporter-legacy-docx-") as temporary:
        markdown_path = Path(temporary) / "conversation.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        result = export_docx(
            markdown_path,
            output_path,
            document_title=str(conversation.get("title_hint") or Path(output_path).stem),
            overwrite=overwrite,
        )

    return CanonicalLegacyDocxResult(
        output_path=result.output_path,
        turn_count=turn_count,
        unknown_turn_count=unknown_count,
        skipped=result.skipped,
    )
