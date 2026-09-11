"""Media inventory library for GPT Exporter archives.

The module is intentionally side-effect free at import time.  It exposes pure
collection/formatting helpers plus one explicit write operation used by the
legacy CLI wrapper and future in-process archive pipeline.
"""

from __future__ import annotations

import json
import lzma
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


TEXT_REPORT_NAME = "inventory-media-report.txt"
JSON_REPORT_NAME = "inventory-media-report.json.xz"
LEGACY_JSON_REPORT_NAME = "inventory-media-report.json"

ProgressCallback = Callable[[str], None]


@dataclass(slots=True)
class _InventoryState:
    pointer_kinds: Counter[str] = field(default_factory=Counter)
    pointer_schemes: Counter[str] = field(default_factory=Counter)
    pointer_examples: defaultdict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list)
    )
    dictation_formats: Counter[str] = field(default_factory=Counter)
    attachment_fields: Counter[str] = field(default_factory=Counter)
    attachment_mime_types: Counter[str] = field(default_factory=Counter)
    attachment_extensions: Counter[str] = field(default_factory=Counter)
    per_file: list[dict[str, object]] = field(default_factory=list)
    summary: Counter[str] = field(default_factory=Counter)


@dataclass(frozen=True, slots=True)
class InventoryResult:
    """Structured result of one inventory run."""

    report: dict[str, object]
    text_report_path: Path
    json_report_path: Path


def _record_pointer(state: _InventoryState, kind: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        return

    state.pointer_kinds[kind] += 1
    scheme = value.split("://", 1)[0].lower() if "://" in value else "no-scheme"
    state.pointer_schemes[scheme] += 1
    if value not in state.pointer_examples[kind] and len(state.pointer_examples[kind]) < 10:
        state.pointer_examples[kind].append(value)


def _inspect_attachment(state: _InventoryState, record: object) -> None:
    if not isinstance(record, dict):
        return

    state.summary["attachment_records"] += 1
    for key in record:
        state.attachment_fields[key] += 1

    for key in ("mime_type", "content_type"):
        value = record.get(key)
        if isinstance(value, str) and "/" in value:
            state.attachment_mime_types[value] += 1

    for key in ("filename", "name"):
        value = record.get(key)
        if isinstance(value, str):
            suffix = Path(value).suffix.lower()
            if suffix:
                state.attachment_extensions[suffix] += 1
                break

    for key in ("asset_pointer", "pointer", "file_id", "download_url", "url"):
        if key in record:
            _record_pointer(state, f"attachment:{key}", record[key])


def _walk(state: _InventoryState, value: object) -> None:
    if isinstance(value, dict):
        content_type = value.get("content_type")
        if content_type == "image_asset_pointer":
            state.summary["image_asset_pointers"] += 1
        elif content_type == "file_asset_pointer":
            state.summary["file_asset_pointers"] += 1
        elif content_type == "audio_asset_pointer":
            state.summary["audio_asset_pointers"] += 1
        elif isinstance(content_type, str) and content_type.endswith("_asset_pointer"):
            state.summary["generic_asset_pointers"] += 1

        for key, child in value.items():
            if key in ("asset_pointer", "pointer", "file_id", "download_url", "url"):
                _record_pointer(state, key, child)
            if key in ("attachments", "assets") and isinstance(child, list):
                for record in child:
                    _inspect_attachment(state, record)
            _walk(state, child)

    elif isinstance(value, list):
        for child in value:
            _walk(state, child)


def _load_conversation(path: Path) -> dict[str, object]:
    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"Conversation root is not a JSON object: {path}")
    return data


def collect_media_inventory(
    downloads_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    """Scan archived conversations and return the v2.8 inventory report model."""

    downloads_dir = Path(downloads_dir)
    state = _InventoryState()

    files = sorted(downloads_dir.glob("*.json.xz"))
    if not files:
        files = sorted(
            path
            for path in downloads_dir.glob("*.json")
            if path.name != "download-index.json"
        )

    for index, path in enumerate(files, 1):
        if progress is not None:
            progress(f"[{index}/{len(files)}] {path.name}")

        data = _load_conversation(path)
        mapping = data.get("mapping", {})
        before = state.summary.copy()

        if isinstance(mapping, dict):
            for node in mapping.values():
                if not isinstance(node, dict):
                    continue
                message = node.get("message")
                if not isinstance(message, dict):
                    continue

                metadata = message.get("metadata")
                if isinstance(metadata, dict):
                    pointer = metadata.get("dictation_asset_pointer")
                    if isinstance(pointer, str) and pointer:
                        state.summary["dictation_assets"] += 1
                        _record_pointer(state, "dictation_asset_pointer", pointer)
                        format_value = metadata.get("dictation_asset_format")
                        if isinstance(format_value, str):
                            state.dictation_formats[format_value.lower()] += 1

                _walk(state, message)

        state.per_file.append(
            {
                "filename": path.name,
                "title": data.get("title"),
                "image_asset_pointers": (
                    state.summary["image_asset_pointers"]
                    - before["image_asset_pointers"]
                ),
                "file_asset_pointers": (
                    state.summary["file_asset_pointers"]
                    - before["file_asset_pointers"]
                ),
                "audio_asset_pointers": (
                    state.summary["audio_asset_pointers"]
                    - before["audio_asset_pointers"]
                ),
                "dictation_assets": (
                    state.summary["dictation_assets"] - before["dictation_assets"]
                ),
                "attachment_records": (
                    state.summary["attachment_records"]
                    - before["attachment_records"]
                ),
            }
        )

    return {
        "summary": dict(state.summary),
        "pointer_kinds": dict(state.pointer_kinds),
        "pointer_schemes": dict(state.pointer_schemes),
        "pointer_examples": dict(state.pointer_examples),
        "dictation_formats": dict(state.dictation_formats),
        "attachment_fields": dict(state.attachment_fields),
        "attachment_mime_types": dict(state.attachment_mime_types),
        "attachment_extensions": dict(state.attachment_extensions),
        "per_file": state.per_file,
    }


def render_text_report(report: dict[str, object]) -> str:
    """Render the human-readable inventory report with v2.8 formatting."""

    summary = Counter(report.get("summary", {}))
    counters = (
        ("Dictation formats", Counter(report.get("dictation_formats", {}))),
        ("Attachment MIME types", Counter(report.get("attachment_mime_types", {}))),
        ("Attachment extensions", Counter(report.get("attachment_extensions", {}))),
        ("Attachment fields", Counter(report.get("attachment_fields", {}))),
        ("Pointer kinds", Counter(report.get("pointer_kinds", {}))),
        ("Pointer schemes", Counter(report.get("pointer_schemes", {}))),
    )

    lines = [
        "ChatGPT Media Inventory",
        "=======================",
        "",
        f"Images      : {summary['image_asset_pointers']}",
        f"Files       : {summary['file_asset_pointers']}",
        f"Audio       : {summary['audio_asset_pointers']}",
        f"Dictations  : {summary['dictation_assets']}",
        f"Attachments : {summary['attachment_records']}",
        "",
    ]

    for title, counter in counters:
        lines.extend([title, "-" * len(title)])
        if counter:
            for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
                lines.append(f"{key}: {count}")
        else:
            lines.append("None")
        lines.append("")

    lines.extend(["Per-file media summary", "----------------------"])
    per_file = report.get("per_file", [])
    if isinstance(per_file, list):
        for item in per_file:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    "",
                    str(item.get("filename", "")),
                    f"  Images      : {item.get('image_asset_pointers', 0)}",
                    f"  Files       : {item.get('file_asset_pointers', 0)}",
                    f"  Audio       : {item.get('audio_asset_pointers', 0)}",
                    f"  Dictations  : {item.get('dictation_assets', 0)}",
                    f"  Attachments : {item.get('attachment_records', 0)}",
                ]
            )

    return "\n".join(lines) + "\n"


def write_inventory_reports(
    report: dict[str, object],
    reports_dir: Path,
) -> tuple[Path, Path]:
    """Write verified compressed JSON and text reports."""

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    text_path = reports_dir / TEXT_REPORT_NAME
    json_path = reports_dir / JSON_REPORT_NAME

    report_raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp_json = json_path.with_name(json_path.name + ".tmp")
    try:
        with lzma.open(temp_json, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(report_raw)
        with lzma.open(temp_json, "rb") as handle:
            if handle.read() != report_raw:
                raise RuntimeError(f"XZ verification failed: {json_path}")
        temp_json.replace(json_path)
    finally:
        if temp_json.exists():
            temp_json.unlink()

    legacy_json = reports_dir / LEGACY_JSON_REPORT_NAME
    if legacy_json.is_file():
        legacy_json.unlink()

    text_path.write_text(render_text_report(report), encoding="utf-8")
    return text_path, json_path


def inventory_media(
    downloads_dir: Path,
    reports_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> InventoryResult:
    """Collect and persist one media inventory run."""

    report = collect_media_inventory(downloads_dir, progress=progress)
    text_path, json_path = write_inventory_reports(report, reports_dir)
    return InventoryResult(
        report=report,
        text_report_path=text_path,
        json_report_path=json_path,
    )


def render_console_summary(result: InventoryResult) -> str:
    """Render the v2.8 terminal summary without printing it."""

    summary = Counter(result.report.get("summary", {}))
    return "\n".join(
        [
            "Media inventory complete",
            "========================",
            f"Images      : {summary['image_asset_pointers']}",
            f"Files       : {summary['file_asset_pointers']}",
            f"Audio       : {summary['audio_asset_pointers']}",
            f"Dictations  : {summary['dictation_assets']}",
            f"Attachments : {summary['attachment_records']}",
            f"Text report : {result.text_report_path}",
            f"JSON report : {result.json_report_path}",
        ]
    )
