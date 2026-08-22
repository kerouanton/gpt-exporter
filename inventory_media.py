import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
INPUT = ARCHIVE_ROOT / "downloads"
REPORTS_DIR = ARCHIVE_ROOT / "reports"
TXT = REPORTS_DIR / "inventory-media-report.txt"
JS = REPORTS_DIR / "inventory-media-report.json.xz"

pointer_kinds = Counter()
pointer_schemes = Counter()
pointer_examples = defaultdict(list)
dictation_formats = Counter()
attachment_fields = Counter()
attachment_mime_types = Counter()
attachment_extensions = Counter()
per_file = []
summary = Counter()


def record_pointer(kind, value):
    if not isinstance(value, str) or not value:
        return
    pointer_kinds[kind] += 1
    scheme = value.split("://", 1)[0].lower() if "://" in value else "no-scheme"
    pointer_schemes[scheme] += 1
    if value not in pointer_examples[kind] and len(pointer_examples[kind]) < 10:
        pointer_examples[kind].append(value)


def inspect_attachment(record):
    if not isinstance(record, dict):
        return
    summary["attachment_records"] += 1
    for key in record:
        attachment_fields[key] += 1
    for key in ("mime_type", "content_type"):
        value = record.get(key)
        if isinstance(value, str) and "/" in value:
            attachment_mime_types[value] += 1
    for key in ("filename", "name"):
        value = record.get(key)
        if isinstance(value, str):
            suffix = Path(value).suffix.lower()
            if suffix:
                attachment_extensions[suffix] += 1
                break
    for key in ("asset_pointer", "pointer", "file_id", "download_url", "url"):
        if key in record:
            record_pointer(f"attachment:{key}", record[key])


def walk(value):
    if isinstance(value, dict):
        ct = value.get("content_type")
        if ct == "image_asset_pointer":
            summary["image_asset_pointers"] += 1
        elif ct == "file_asset_pointer":
            summary["file_asset_pointers"] += 1
        elif ct == "audio_asset_pointer":
            summary["audio_asset_pointers"] += 1
        elif isinstance(ct, str) and ct.endswith("_asset_pointer"):
            summary["generic_asset_pointers"] += 1

        for key, child in value.items():
            if key in ("asset_pointer", "pointer", "file_id", "download_url", "url"):
                record_pointer(key, child)
            if key in ("attachments", "assets") and isinstance(child, list):
                for record in child:
                    inspect_attachment(record)
            walk(child)

    elif isinstance(value, list):
        for child in value:
            walk(child)


REPORTS_DIR.mkdir(parents=True, exist_ok=True)

files = sorted(INPUT.glob("*.json.xz"))
if not files:
    files = sorted(
        p for p in INPUT.glob("*.json")
        if p.name != "download-index.json"
    )

for index, path in enumerate(files, 1):
    print(f"[{index}/{len(files)}] {path.name}")
    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    mapping = data.get("mapping", {})
    before = summary.copy()

    for node in mapping.values():
        message = node.get("message")
        if not isinstance(message, dict):
            continue

        metadata = message.get("metadata")
        if isinstance(metadata, dict):
            pointer = metadata.get("dictation_asset_pointer")
            if isinstance(pointer, str) and pointer:
                summary["dictation_assets"] += 1
                record_pointer("dictation_asset_pointer", pointer)
                fmt = metadata.get("dictation_asset_format")
                if isinstance(fmt, str):
                    dictation_formats[fmt.lower()] += 1

        walk(message)

    per_file.append({
        "filename": path.name,
        "title": data.get("title"),
        "image_asset_pointers": summary["image_asset_pointers"] - before["image_asset_pointers"],
        "file_asset_pointers": summary["file_asset_pointers"] - before["file_asset_pointers"],
        "audio_asset_pointers": summary["audio_asset_pointers"] - before["audio_asset_pointers"],
        "dictation_assets": summary["dictation_assets"] - before["dictation_assets"],
        "attachment_records": summary["attachment_records"] - before["attachment_records"],
    })

report = {
    "summary": dict(summary),
    "pointer_kinds": dict(pointer_kinds),
    "pointer_schemes": dict(pointer_schemes),
    "pointer_examples": dict(pointer_examples),
    "dictation_formats": dict(dictation_formats),
    "attachment_fields": dict(attachment_fields),
    "attachment_mime_types": dict(attachment_mime_types),
    "attachment_extensions": dict(attachment_extensions),
    "per_file": per_file,
}

report_raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
temp_js = JS.with_name(JS.name + ".tmp")
with lzma.open(temp_js, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
    handle.write(report_raw)
with lzma.open(temp_js, "rb") as handle:
    if handle.read() != report_raw:
        raise RuntimeError(f"XZ verification failed: {JS}")
temp_js.replace(JS)
legacy_js = REPORTS_DIR / "inventory-media-report.json"
if legacy_js.is_file():
    legacy_js.unlink()

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

for title, counter in (
    ("Dictation formats", dictation_formats),
    ("Attachment MIME types", attachment_mime_types),
    ("Attachment extensions", attachment_extensions),
    ("Attachment fields", attachment_fields),
    ("Pointer kinds", pointer_kinds),
    ("Pointer schemes", pointer_schemes),
):
    lines.extend([title, "-" * len(title)])
    if counter:
        for key, count in sorted(counter.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"{key}: {count}")
    else:
        lines.append("None")
    lines.append("")

lines.extend(["Per-file media summary", "----------------------"])
for item in per_file:
    lines.extend([
        "",
        item["filename"],
        f"  Images      : {item['image_asset_pointers']}",
        f"  Files       : {item['file_asset_pointers']}",
        f"  Audio       : {item['audio_asset_pointers']}",
        f"  Dictations  : {item['dictation_assets']}",
        f"  Attachments : {item['attachment_records']}",
    ])

TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

print()
print("Media inventory complete")
print("========================")
print(f"Images      : {summary['image_asset_pointers']}")
print(f"Files       : {summary['file_asset_pointers']}")
print(f"Audio       : {summary['audio_asset_pointers']}")
print(f"Dictations  : {summary['dictation_assets']}")
print(f"Attachments : {summary['attachment_records']}")
print(f"Text report : {TXT}")
print(f"JSON report : {JS}")
