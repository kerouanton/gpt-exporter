"""Generate normalized DOCX derivatives from reconstructed legacy turns."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from docx import Document

from gpt_exporter.export.docx import export_docx
from gpt_exporter.legacy.assets import (
    LEGACY_ASSET_EXPORT_VERSION,
    LegacyAsset,
    LegacyAssetExport,
    extract_legacy_assets,
)


CANONICAL_LEGACY_DOCX_VERSION = "legacy-canonical-docx-v4"


@dataclass(frozen=True, slots=True)
class CanonicalLegacyDocxResult:
    output_path: Path
    turn_count: int
    unknown_turn_count: int
    skipped: bool
    source_text_restored: bool
    asset_count: int
    image_count: int
    attachment_count: int
    unresolved_asset_count: int


def _markdown_escape_line(value: str) -> str:
    """Avoid accidental top-level Markdown syntax in metadata values."""
    return value.replace("\r", " ").replace("\n", " ").strip()


def _markdown_label(value: str) -> str:
    return value.replace("[", "(").replace("]", ")").replace("\r", " ").replace("\n", " ").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_source_sha(source: Path, conversation: dict[str, Any]) -> Path:
    expected_sha = str(conversation.get("source_sha256") or "").strip().lower()
    if expected_sha and len(expected_sha) == 64:
        actual_sha = _sha256(source)
        if actual_sha != expected_sha:
            raise ValueError(
                f"SHA-256 mismatch for source DOCX {source}: "
                f"expected {expected_sha}, got {actual_sha}"
            )
    return source.resolve()


def _resolve_source_docx(
    conversation: dict[str, Any],
    docx_root: Path | None,
) -> Path | None:
    """Locate the immutable historical DOCX used to restore text and assets."""
    source_filename = str(conversation.get("source_filename") or "").strip()

    if docx_root is not None:
        root = Path(docx_root).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"Legacy DOCX root does not exist: {root}")
        if not source_filename:
            raise ValueError("Legacy conversation is missing source_filename")

        direct = root / source_filename
        if direct.is_file():
            return _verify_source_sha(direct, conversation)

        matches = list(root.rglob(source_filename))
        if not matches:
            raise FileNotFoundError(
                f"Legacy source DOCX not found under {root}: {source_filename}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Multiple legacy DOCX files match {source_filename}: {matches}"
            )
        return _verify_source_sha(matches[0], conversation)

    source_path = str(conversation.get("source_path") or "").strip()
    if source_path:
        candidate = Path(source_path).expanduser()
        if candidate.is_file():
            return _verify_source_sha(candidate, conversation)
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


def _asset_markdown(asset: LegacyAsset, markdown_base: Path) -> str:
    relative = os.path.relpath(asset.output_path.resolve(), markdown_base.resolve())
    target = quote(Path(relative).as_posix(), safe="/._-~")
    name = _markdown_label(PurePosixPath(asset.source_part_name).name or asset.output_path.name)
    if asset.kind == "image":
        return f"![Legacy image: {name}]({target})"
    return f"[📎 Archived attachment: {name}]({target})"


def _turn_bounds(turn: dict[str, Any]) -> tuple[int | None, int | None]:
    first = turn.get("first_order")
    last = turn.get("last_order")
    return (
        first if isinstance(first, int) else None,
        last if isinstance(last, int) else None,
    )


def _assign_assets_to_turns(
    turns: list[dict[str, Any]],
    assets: tuple[LegacyAsset, ...],
) -> dict[int, list[LegacyAsset]]:
    """Assign media-only Word blocks to the nearest reconstructed turn.

    Assets inside a turn's known Word span are exact.  An asset in a gap is
    conservatively attached to the preceding turn (or the first turn when it
    precedes all reconstructed content), preserving document order without
    inventing a new User/Assistant role.
    """
    assignments: dict[int, list[LegacyAsset]] = {index: [] for index in range(len(turns))}
    if not turns:
        return assignments

    bounds = [_turn_bounds(turn) for turn in turns]
    for asset in assets:
        chosen: int | None = None
        for index, (first, last) in enumerate(bounds):
            if first is not None and last is not None and first <= asset.block_order <= last:
                chosen = index
                break
        if chosen is None:
            preceding = [
                (first, index)
                for index, (first, _) in enumerate(bounds)
                if first is not None and first <= asset.block_order
            ]
            chosen = max(preceding)[1] if preceding else 0
        assignments[chosen].append(asset)

    for values in assignments.values():
        values.sort(key=lambda asset: (asset.block_order, asset.relationship_id))
    return assignments


def _turn_body(
    turn: dict[str, Any],
    source_blocks: dict[int, str] | None,
    assets: list[LegacyAsset],
    markdown_base: Path | None,
) -> str:
    """Restore Word block text and interleave exported assets by source order."""
    if source_blocks is None:
        body = str(turn.get("content") or "").strip()
        if assets and markdown_base is not None:
            media = "\n\n".join(_asset_markdown(asset, markdown_base) for asset in assets)
            return "\n\n".join(part for part in (body, media) if part)
        return body

    source_orders = turn.get("source_orders")
    orders = [order for order in source_orders if isinstance(order, int)] if isinstance(source_orders, list) else []
    first, last = _turn_bounds(turn)
    if first is not None and last is not None:
        orders.extend(order for order in source_blocks if first <= order <= last and order not in orders)
    orders = sorted(set(orders))

    assets_by_order: dict[int, list[LegacyAsset]] = {}
    for asset in assets:
        assets_by_order.setdefault(asset.block_order, []).append(asset)

    all_orders = sorted(set(orders) | set(assets_by_order))
    parts: list[str] = []
    for order in all_orders:
        text = source_blocks.get(order)
        if text:
            parts.append(text)
        if markdown_base is not None:
            parts.extend(_asset_markdown(asset, markdown_base) for asset in assets_by_order.get(order, []))

    if parts:
        return "\n\n".join(parts).strip()
    return str(turn.get("content") or "").strip()


def build_legacy_markdown(
    conversation: dict[str, Any],
    *,
    source_docx: Path | None = None,
    asset_export: LegacyAssetExport | None = None,
    markdown_base: Path | None = None,
) -> str:
    """Build Markdown consumed by the normal GPT Exporter DOCX renderer.

    Text and role boundaries come from the validated legacy-turn JSON.  When
    the immutable source DOCX is available, original Word block text is re-read
    and exported images/embedded packages are interleaved by Word block order.
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
    assets = asset_export.assets if asset_export is not None else ()

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
        f"- Asset exporter: `{LEGACY_ASSET_EXPORT_VERSION}`",
        f"- Canonical DOCX renderer: `{CANONICAL_LEGACY_DOCX_VERSION}`",
        f"- Text rendering: `{'source Word blocks restored' if source_blocks is not None else 'normalized turns fallback'}`",
        f"- Preserved assets: `{len(assets)}`",
    ]
    if asset_export is not None and asset_export.unresolved_relationships:
        lines.append(f"- Unresolved embedded relationships: `{len(asset_export.unresolved_relationships)}`")
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

    raw_turns = conversation.get("turns")
    if not isinstance(raw_turns, list):
        raise ValueError(f"Invalid normalized turns for {source_filename}")
    turns = [turn for turn in raw_turns if isinstance(turn, dict)]
    assigned_assets = _assign_assets_to_turns(turns, assets)

    unknown_count = sum(str(turn.get("role") or "unknown") == "unknown" for turn in turns)
    if unknown_count:
        lines.extend(
            [
                "",
                f"> **Reconstruction note:** {unknown_count} turn(s) remain `UNKNOWN` because the historical Word evidence was not strong enough to assign a role safely.",
            ]
        )
    if asset_export is not None and asset_export.unresolved_relationships:
        lines.extend(
            [
                "",
                f"> **Asset note:** {len(asset_export.unresolved_relationships)} embedded relationship(s) could not be exported and remain available only in the historical DOCX.",
            ]
        )

    lines.extend(["", "---", ""])

    role_titles = {"user": "User", "assistant": "Assistant", "unknown": "Unknown"}
    emitted = 0
    for index, turn in enumerate(turns):
        body = _turn_body(
            turn,
            source_blocks,
            assigned_assets.get(index, []),
            markdown_base,
        )
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
    """Export one reconstructed derivative through JSON -> Markdown -> DOCX."""
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
    source_sha = str(conversation.get("source_sha256") or "").strip().lower()
    asset_export = LegacyAssetExport(assets=(), unresolved_relationships=())
    if source_docx is not None:
        if len(source_sha) != 64:
            source_sha = _sha256(source_docx)
        asset_export = extract_legacy_assets(
            source_docx,
            output_dir / "assets" / "legacy",
            source_sha256=source_sha,
        )

    # Keep Markdown transient, but place it below output_dir so all asset links
    # are ordinary relative paths.  The existing Markdown -> DOCX converter is
    # therefore used unchanged for both native and legacy rendering.
    with tempfile.TemporaryDirectory(prefix=".legacy-md-", dir=output_dir) as temporary:
        markdown_path = Path(temporary) / "conversation.md"
        markdown = build_legacy_markdown(
            conversation,
            source_docx=source_docx,
            asset_export=asset_export,
            markdown_base=markdown_path.parent,
        )
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
        asset_count=len(asset_export.assets),
        image_count=asset_export.image_count,
        attachment_count=asset_export.attachment_count,
        unresolved_asset_count=len(asset_export.unresolved_relationships),
    )
