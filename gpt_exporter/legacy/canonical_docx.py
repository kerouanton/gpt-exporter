"""Generate normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx import Document

from gpt_exporter.export.docx import export_docx


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v3"


@dataclass(frozen=True, slots=True)
class CanonicalLegacyDocxResult:
    output_path: Path
    turn_count: int
    unknown_turn_count: int
    skipped: bool
    source_text_restored: bool


def _markdown_escape_line(value: str) -> str:
    """Avoid accidental top-level Markdown syntax in metadata values."""
    return value.replace("\r", " ").replace("\n", " ").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source_docx(
    conversation: dict[str, Any],
    docx_root: Path | None,
) -> Path | None:
    """Locate the immutable historical DOCX used to restore display whitespace."""
    source_filename = str(conversation.get("source_filename") or "").strip()
    candidates: list[Path] = []
    if docx_root is not None and source_filename:
        candidates.append(Path(docx_root).expanduser() / source_filename)
    source_path = str(conversation.get("source_path") or "").strip()
    if source_path:
        candidates.append(Path(source_path).expanduser())

    for candidate in candidates:
        if candidate.is_file():
            source = candidate.resolve()
            expected_sha = str(conversation.get("source_sha256") or "").strip().lower()
            if expected_sha and len(expected_sha) == 64:
                actual_sha = _sha256(source)
                if actual_sha != expected_sha:
                    raise ValueError(
                        f"SHA-256 mismatch for source DOCX {source}: "
                        f"expected {expected_sha}, got {actual_sha}"
                    )
            return source
    return None


def _source_block_texts(source_docx: Path) -> dict[int, str]:
    """Read source Word block text without collapsing manual line breaks."""
    document = Document(source_docx)
    result: dict[int, str] = {}
    for order, item in enumerate(document.iter_inner_content()):
        if hasattr(item, "rows"):
            rows: list[str] = []
            for row in item.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(" | ".join(cells))
            text = "\n".join(row for row in rows if row.strip(" |"))
        else:
            text = str(item.text or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if text:
            result[order] = text
    return result


def _turn_body(turn: dict[str, Any], source_blocks: dict[int, str] | None) -> str:
    """Prefer raw Word text for known source blocks; fall back to normalized turns."""
    if source_blocks is not None:
        source_orders = turn.get("source_orders")
        if isinstance(source_orders, list):
            restored = [
                source_blocks[order]
                for order in source_orders
                if isinstance(order, int) and order in source_blocks
            ]
            if restored:
                return "\n\n".join(restored).strip()
    return str(turn.get("content") or "").strip()


def build_legacy_markdown(
    conversation: dict[str, Any],
    *,
    source_docx: Path | None = None,
) -> str:
    """Build a conservative text-only Markdown derivative.

    The DOCX exporter receives the title separately through ``document_title``
    so no Markdown H1 is emitted here.  When the immutable source DOCX is
    available, its original Word block text is re-read by ``source_orders`` so
    manual line breaks survive presentation rendering.  Role inference and
    turn boundaries still come exclusively from the validated turns JSON.

    Images and embedded attachments remain out of scope for this pass.
    """
    source_filename = str(conversation.get("source_filename") or "unknown").strip()
    source_sha = str(conversation.get("source_sha256") or "unknown").strip()
    category = str(conversation.get("category_hint") or "").strip()
    date_hint = str(conversation.get("date_hint") or "").strip()
    parser_version = str(conversation.get("parser_version") or "unknown").strip()
    role_version = str(conversation.get("role_inference_version") or "unknown").strip()
    turn_version = str(conversation.get("turn_builder_version") or "unknown").strip()
    starts_mid = conversation.get("starts_mid_conversation")
    source_blocks = _source_block_texts(source_docx) if source_docx is not None else None

    lines = [
        "> **Legacy DOCX normalized derivative (text-only).** This document was reconstructed from an immutable historical Word capture. The historical DOCX remains the authoritative source.",
        "",
        "> **Media scope:** images, embedded files, and other attachments from the historical DOCX are not included in this normalized derivative yet. Consult the source DOCX for those items.",
        "",
        "## Provenance",
        "",
        f"- Source file: `{_markdown_escape_line(source_filename)}`",
        f"- Source SHA-256: `{_markdown_escape_line(source_sha)}`",
        f"- Parser: `{_markdown_escape_line(parser_version)}`",
        f"- Role inference: `{_markdown_escape_line(role_version)}`",
        f"- Turn builder: `{_markdown_escape_line(turn_version)}`",
        f"- Canonical DOCX renderer: `{CANONICAL_LEGACY_DOCX_VERSION}`",
        f"- Text rendering: `{'source Word blocks restored' if source_blocks is not None else 'normalized turns fallback'}`",
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
        body = _turn_body(turn, source_blocks)
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
    docx_root: Path | None = None,
) -> CanonicalLegacyDocxResult:
    """Export one normalized text-only derivative without touching its source."""
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

    source_docx = _resolve_source_docx(conversation, docx_root)
    markdown = build_legacy_markdown(conversation, source_docx=source_docx)
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
        source_text_restored=source_docx is not None,
    )