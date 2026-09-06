"""Audit semantic preservation from immutable legacy DOCX to normalized DOCX.

This intentionally does NOT compare pagination or Word-specific styling. It
checks only information that GPT Exporter's modern Markdown -> DOCX pipeline
can represent: text structure, headings, lists, inline emphasis, hyperlinks,
tables, and recoverable embedded assets.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from docx import Document


NORMALIZED_SUFFIX = " [normalized]"
IMAGE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
OLE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
PACKAGE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _style_name(paragraph) -> str:
    try:
        return str(paragraph.style.name or "")
    except (AttributeError, KeyError):
        return ""


def _heading_count(document: Document) -> int:
    return sum(
        1
        for paragraph in document.paragraphs
        if _style_name(paragraph).casefold().startswith(("heading ", "titre "))
    )


def _list_count(document: Document) -> int:
    count = 0
    for paragraph in document.paragraphs:
        p_pr = paragraph._p.pPr
        has_num = p_pr is not None and p_pr.numPr is not None
        style = _style_name(paragraph).casefold()
        if has_num or style.startswith(("list bullet", "list number", "liste à puces", "liste num")):
            count += 1
    return count


def _all_paragraphs(document: Document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def _hyperlink_count(document: Document) -> int:
    return sum(len(paragraph._p.xpath(".//w:hyperlink")) for paragraph in _all_paragraphs(document))


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _style_key(style) -> str:
    """Return a stable key for python-docx style proxy objects."""
    try:
        style_id = str(style.style_id or "")
    except (AttributeError, KeyError):
        style_id = ""
    if style_id:
        return style_id
    try:
        return str(style.name or "")
    except (AttributeError, KeyError):
        return ""


def _style_flag(
    style,
    attribute: str,
    cache: dict[tuple[str, str], bool | None],
) -> bool | None:
    """Resolve a character-style font boolean through its base-style chain."""
    if style is None:
        return None

    key = (_style_key(style), attribute)
    if key in cache:
        return cache[key]

    visited: set[str] = set()
    current = style
    result: bool | None = None
    while current is not None:
        current_key = _style_key(current)
        if current_key in visited:
            break
        visited.add(current_key)
        try:
            value = getattr(current.font, attribute)
        except (AttributeError, KeyError):
            value = None
        if value is not None:
            result = bool(value)
            break
        try:
            current = current.base_style
        except (AttributeError, KeyError):
            current = None

    cache[key] = result
    return result


def _effective_inline_flag(
    run,
    attribute: str,
    cache: dict[tuple[str, str], bool | None],
) -> bool:
    """Resolve inline emphasis exactly as the legacy Markdown converter does.

    Direct run formatting and inherited character-style formatting are inline
    semantics. Paragraph-style formatting is deliberately excluded: headings,
    lists and other paragraph semantics are represented by Markdown block
    structure and rendered by the standard DOCX style system.
    """
    direct = getattr(run, attribute)
    if direct is not None:
        return bool(direct)

    try:
        character_style = run.style
    except (AttributeError, KeyError):
        character_style = None
    character_value = _style_flag(character_style, attribute, cache)
    return bool(character_value) if character_value is not None else False


def _flush_span(parts: list[str], target: Counter[str]) -> None:
    if not parts:
        return
    value = _normalized_text("".join(parts))
    if len(value) >= 2:
        target[value] += 1
    parts.clear()


def _emphasis_spans(document: Document) -> tuple[Counter[str], Counter[str]]:
    """Collect bold and italic inline spans in one pass through all runs."""
    bold_spans: Counter[str] = Counter()
    italic_spans: Counter[str] = Counter()
    style_cache: dict[tuple[str, str], bool | None] = {}

    for paragraph in _all_paragraphs(document):
        current_bold: list[str] = []
        current_italic: list[str] = []
        for run in paragraph.runs:
            text = str(run.text or "")

            if _effective_inline_flag(run, "bold", style_cache):
                current_bold.append(text)
            else:
                _flush_span(current_bold, bold_spans)

            if _effective_inline_flag(run, "italic", style_cache):
                current_italic.append(text)
            else:
                _flush_span(current_italic, italic_spans)

        _flush_span(current_bold, bold_spans)
        _flush_span(current_italic, italic_spans)

    return bold_spans, italic_spans


def _missing_emphasis(source: Counter[str], normalized: Counter[str]) -> list[str]:
    normalized_spans = [value.casefold() for value in normalized]
    missing: list[str] = []
    for source_text in source:
        needle = source_text.casefold()
        if not any(
            needle in candidate or candidate in needle
            for candidate in normalized_spans
            if candidate
        ):
            missing.append(source_text)
    return missing[:20]


def _literal_br_cells(document: Document) -> int:
    return sum(
        1
        for table in document.tables
        for row in table.rows
        for cell in row.cells
        if "<br>" in cell.text.casefold()
    )


def _relationship_payloads(document: Document) -> tuple[list[str], list[str]]:
    images: list[str] = []
    attachments: list[str] = []
    seen: set[tuple[str, str]] = set()
    for rel in document.part.rels.values():
        reltype = str(rel.reltype)
        if reltype not in {IMAGE_REL, OLE_REL, PACKAGE_REL}:
            continue
        target = getattr(rel, "target_part", None)
        blob = getattr(target, "blob", None)
        if not isinstance(blob, bytes):
            continue
        digest = _sha256_bytes(blob)
        key = (reltype, digest)
        if key in seen:
            continue
        seen.add(key)
        if reltype == IMAGE_REL:
            images.append(digest)
        else:
            attachments.append(digest)
    return images, attachments


def _asset_hashes(asset_dir: Path) -> set[str]:
    hashes: set[str] = set()
    if asset_dir.is_dir():
        for path in asset_dir.rglob("*"):
            if path.is_file():
                try:
                    hashes.add(_sha256_file(path))
                except OSError:
                    pass
    return hashes


def _normalized_path(output_dir: Path, source: Path) -> Path:
    return output_dir / f"{source.stem}{NORMALIZED_SUFFIX}.docx"


def audit_pair(source: Path, normalized: Path, output_dir: Path) -> dict[str, object]:
    phase_started = time.perf_counter()
    source_doc = Document(source)
    normalized_doc = Document(normalized)
    open_elapsed = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    source_images, source_attachments = _relationship_payloads(source_doc)
    normalized_images, _ = _relationship_payloads(normalized_doc)
    source_sha = _sha256_file(source)
    asset_dir = output_dir / "assets" / "legacy" / source_sha[:16]
    exported_hashes = _asset_hashes(asset_dir)
    assets_elapsed = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    source_bold, source_italic = _emphasis_spans(source_doc)
    normalized_bold, normalized_italic = _emphasis_spans(normalized_doc)
    emphasis_elapsed = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    source_tables = len(source_doc.tables)
    normalized_tables = len(normalized_doc.tables)
    source_headings = _heading_count(source_doc)
    normalized_headings = _heading_count(normalized_doc)
    source_lists = _list_count(source_doc)
    normalized_lists = _list_count(normalized_doc)
    source_links = _hyperlink_count(source_doc)
    normalized_links = _hyperlink_count(normalized_doc)
    literal_br_cells = _literal_br_cells(normalized_doc)
    structure_elapsed = time.perf_counter() - phase_started

    phase_started = time.perf_counter()
    missing_asset_hashes = sorted((set(source_images) | set(source_attachments)) - exported_hashes)
    missing_bold = _missing_emphasis(source_bold, normalized_bold)
    missing_italic = _missing_emphasis(source_italic, normalized_italic)

    failures: list[str] = []
    warnings: list[str] = []
    if normalized_tables < source_tables:
        failures.append(f"tables {normalized_tables} < {source_tables}")
    if normalized_headings < source_headings:
        failures.append(f"headings {normalized_headings} < {source_headings}")
    if normalized_lists < source_lists:
        failures.append(f"lists {normalized_lists} < {source_lists}")
    if source_images and len(normalized_images) < len(source_images):
        failures.append(f"embedded images {len(normalized_images)} < {len(source_images)}")
    if missing_asset_hashes:
        failures.append(f"{len(missing_asset_hashes)} source asset payload(s) missing from exported assets")
    if normalized_links < source_links:
        warnings.append(f"hyperlinks {normalized_links} < {source_links}")
    if missing_bold:
        warnings.append(f"bold spans not found: {len(missing_bold)}")
    if missing_italic:
        warnings.append(f"italic spans not found: {len(missing_italic)}")
    if literal_br_cells:
        warnings.append(f"literal <br> text in {literal_br_cells} table cell(s)")

    status = "FAIL" if failures else ("WARN" if warnings else "PASS")
    compare_elapsed = time.perf_counter() - phase_started

    result = {
        "source": source.name,
        "normalized": normalized.name,
        "status": status,
        "source_tables": source_tables,
        "normalized_tables": normalized_tables,
        "source_headings": source_headings,
        "normalized_headings": normalized_headings,
        "source_lists": source_lists,
        "normalized_lists": normalized_lists,
        "source_hyperlinks": source_links,
        "normalized_hyperlinks": normalized_links,
        "source_images": len(source_images),
        "normalized_images": len(normalized_images),
        "source_attachments": len(source_attachments),
        "exported_asset_files": len([p for p in asset_dir.rglob("*") if p.is_file()]) if asset_dir.is_dir() else 0,
        "literal_br_cells": literal_br_cells,
        "missing_bold_examples": missing_bold,
        "missing_italic_examples": missing_italic,
        "failures": failures,
        "warnings": warnings,
        "timing_open_s": round(open_elapsed, 3),
        "timing_assets_s": round(assets_elapsed, 3),
        "timing_emphasis_s": round(emphasis_elapsed, 3),
        "timing_structure_s": round(structure_elapsed, 3),
        "timing_compare_s": round(compare_elapsed, 3),
    }

    # Drop the large lxml/python-docx trees before returning. Cyclic structures
    # can otherwise accumulate and trigger very long GC pauses between files.
    del source_doc
    del normalized_doc
    gc.collect()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit semantic parity of legacy normalized DOCX files")
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--normalized-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=Path("legacy-semantic-audit.json"))
    parser.add_argument("--csv", type=Path, default=Path("legacy-semantic-audit.csv"))
    args = parser.parse_args(argv)

    source_dir = args.source_dir.expanduser().resolve()
    output_dir = args.normalized_dir.expanduser().resolve()
    sources = sorted(path for path in source_dir.glob("*.docx") if NORMALIZED_SUFFIX not in path.stem)
    results: list[dict[str, object]] = []
    missing_normalized: list[str] = []
    total_started = time.perf_counter()

    for index, source in enumerate(sources, start=1):
        normalized = _normalized_path(output_dir, source)
        if not normalized.is_file():
            missing_normalized.append(normalized.name)
            continue

        started = time.perf_counter()
        print(f"[{_stamp()}] START {index:02}/{len(sources):02} {source.name}", flush=True)
        result = audit_pair(source, normalized, output_dir)
        elapsed = time.perf_counter() - started
        results.append(result)

        print(
            f"[{_stamp()}] {result['status']:4}  {elapsed:7.2f}s {source.name} "
            f"[open={result['timing_open_s']:.2f}s assets={result['timing_assets_s']:.2f}s "
            f"emphasis={result['timing_emphasis_s']:.2f}s structure={result['timing_structure_s']:.2f}s "
            f"compare={result['timing_compare_s']:.2f}s]",
            flush=True,
        )
        for problem in result["failures"]:
            print(f"      FAIL: {problem}")
        for warning in result["warnings"]:
            print(f"      WARN: {warning}")

    summary = {
        "source_count": len(sources),
        "audited_count": len(results),
        "missing_normalized": missing_normalized,
        "pass": sum(result["status"] == "PASS" for result in results),
        "warn": sum(result["status"] == "WARN" for result in results),
        "fail": sum(result["status"] == "FAIL" for result in results),
    }
    payload = {"schema": "gpt-exporter-legacy-semantic-audit-v5", "summary": summary, "results": results}
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fieldnames = [
        "source", "normalized", "status", "source_tables", "normalized_tables",
        "source_headings", "normalized_headings", "source_lists", "normalized_lists",
        "source_hyperlinks", "normalized_hyperlinks", "source_images", "normalized_images",
        "source_attachments", "exported_asset_files", "literal_br_cells",
        "timing_open_s", "timing_assets_s", "timing_emphasis_s", "timing_structure_s",
        "timing_compare_s", "failures", "warnings",
    ]
    with args.csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {name: result.get(name, "") for name in fieldnames}
            row["failures"] = "; ".join(result["failures"])
            row["warnings"] = "; ".join(result["warnings"])
            writer.writerow(row)

    total_elapsed = time.perf_counter() - total_started
    print("\nSemantic audit summary\n======================")
    print(f"Sources : {summary['source_count']}")
    print(f"Audited : {summary['audited_count']}")
    print(f"PASS    : {summary['pass']}")
    print(f"WARN    : {summary['warn']}")
    print(f"FAIL    : {summary['fail']}")
    print(f"Missing : {len(missing_normalized)}")
    print(f"Elapsed : {total_elapsed:.2f}s")
    print(f"JSON    : {args.json.resolve()}")
    print(f"CSV     : {args.csv.resolve()}")
    return 1 if summary["fail"] or missing_normalized else 0


if __name__ == "__main__":
    raise SystemExit(main())
