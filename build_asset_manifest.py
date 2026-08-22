import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
INPUT_DIR = ARCHIVE_ROOT / "downloads"
REPORTS_DIR = ARCHIVE_ROOT / "reports"

OUTPUT_JSON = REPORTS_DIR / "asset-manifest.json.xz"
OUTPUT_TXT = REPORTS_DIR / "asset-manifest.txt"

def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def add_unique(items: dict[str, dict[str, Any]], key: str, record: dict[str, Any]) -> None:
    if key not in items:
        items[key] = record


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(INPUT_DIR.glob("*.json.xz"))
    if not files:
        files = sorted(
            path for path in INPUT_DIR.glob("*.json")
            if path.name != "download-index.json"
        )

    if not files:
        print(f"No conversation JSON files found in: {INPUT_DIR}")
        return 1

    images: dict[str, dict[str, Any]] = {}
    dictations: dict[str, dict[str, Any]] = {}
    attachments: dict[str, dict[str, Any]] = {}

    raw_counts = Counter()

    for index, path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] {path.name}")

        if path.name.lower().endswith(".json.xz"):
            with lzma.open(path, "rt", encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        conversation_id = data.get("conversation_id")
        title = data.get("title")
        mapping = data.get("mapping", {})

        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue

            message = node.get("message")
            if not isinstance(message, dict):
                continue

            message_id = message.get("id")
            metadata = message.get("metadata")
            content = message.get("content")

            if isinstance(metadata, dict):
                pointer = metadata.get("dictation_asset_pointer")
                if isinstance(pointer, str) and pointer:
                    raw_counts["dictation_pointer_occurrences"] += 1
                    add_unique(
                        dictations,
                        pointer,
                        {
                            "pointer": pointer,
                            "format": metadata.get("dictation_asset_format"),
                            "conversation_id": conversation_id,
                            "conversation_title": title,
                            "source_file": path.name,
                            "node_id": node_id,
                            "message_id": message_id,
                        },
                    )

                attachment_list = metadata.get("attachments")
                if isinstance(attachment_list, list):
                    for item in attachment_list:
                        if not isinstance(item, dict):
                            continue

                        raw_counts["attachment_occurrences"] += 1

                        attachment_id = item.get("id")
                        name = item.get("name")
                        key = str(
                            attachment_id
                            or item.get("library_file_id")
                            or f"{conversation_id}:{message_id}:{name}"
                        )

                        add_unique(
                            attachments,
                            key,
                            {
                                "id": attachment_id,
                                "library_file_id": item.get("library_file_id"),
                                "name": name,
                                "size": item.get("size"),
                                "mime_type": (
                                    item.get("mime_type")
                                    or item.get("mimeType")
                                ),
                                "width": item.get("width"),
                                "height": item.get("height"),
                                "source": item.get("source"),
                                "attachment_role": item.get("attachment_role"),
                                "conversation_id": conversation_id,
                                "conversation_title": title,
                                "source_file": path.name,
                                "node_id": node_id,
                                "message_id": message_id,
                            },
                        )

            for obj in iter_dicts(content):
                if obj.get("content_type") != "image_asset_pointer":
                    continue

                pointer = obj.get("asset_pointer")
                if not isinstance(pointer, str) or not pointer:
                    continue

                raw_counts["image_pointer_occurrences"] += 1

                add_unique(
                    images,
                    pointer,
                    {
                        "pointer": pointer,
                        "width": obj.get("width"),
                        "height": obj.get("height"),
                        "size_bytes": obj.get("size_bytes"),
                        "conversation_id": conversation_id,
                        "conversation_title": title,
                        "source_file": path.name,
                        "node_id": node_id,
                        "message_id": message_id,
                    },
                )

    mime_types = Counter(
        str(item.get("mime_type"))
        for item in attachments.values()
        if item.get("mime_type")
    )

    extensions = Counter()
    for item in attachments.values():
        name = item.get("name")
        if isinstance(name, str):
            suffix = Path(name).suffix.lower()
            if suffix:
                extensions[suffix] += 1

    manifest = {
        "summary": {
            "conversation_files": len(files),
            "unique_images": len(images),
            "unique_dictations": len(dictations),
            "unique_attachments": len(attachments),
            "raw_image_pointer_occurrences": raw_counts[
                "image_pointer_occurrences"
            ],
            "raw_dictation_pointer_occurrences": raw_counts[
                "dictation_pointer_occurrences"
            ],
            "raw_attachment_occurrences": raw_counts[
                "attachment_occurrences"
            ],
        },
        "attachment_mime_types": dict(
            sorted(mime_types.items(), key=lambda x: (-x[1], x[0]))
        ),
        "attachment_extensions": dict(
            sorted(extensions.items(), key=lambda x: (-x[1], x[0]))
        ),
        "images": list(images.values()),
        "dictations": list(dictations.values()),
        "attachments": list(attachments.values()),
    }

    manifest_raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temp_json = OUTPUT_JSON.with_name(OUTPUT_JSON.name + ".tmp")
    with lzma.open(temp_json, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
        handle.write(manifest_raw)
    with lzma.open(temp_json, "rb") as handle:
        if handle.read() != manifest_raw:
            raise RuntimeError(f"XZ verification failed: {OUTPUT_JSON}")
    temp_json.replace(OUTPUT_JSON)
    legacy_json = REPORTS_DIR / "asset-manifest.json"
    if legacy_json.is_file():
        legacy_json.unlink()

    lines = [
        "ChatGPT Asset Manifest",
        "======================",
        "",
        f"Conversation files             : {len(files)}",
        f"Unique images                  : {len(images)}",
        f"Unique dictations              : {len(dictations)}",
        f"Unique attachments             : {len(attachments)}",
        f"Raw image pointer occurrences  : {raw_counts['image_pointer_occurrences']}",
        f"Raw dictation occurrences      : {raw_counts['dictation_pointer_occurrences']}",
        f"Raw attachment occurrences     : {raw_counts['attachment_occurrences']}",
        "",
        "Attachment MIME types",
        "---------------------",
    ]

    for key, count in sorted(mime_types.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"{key}: {count}")

    lines.extend(["", "Attachment extensions", "---------------------"])

    for key, count in sorted(extensions.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"{key}: {count}")

    OUTPUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print()
    print("Asset manifest complete")
    print("=======================")
    print(f"Unique images      : {len(images)}")
    print(f"Unique dictations  : {len(dictations)}")
    print(f"Unique attachments : {len(attachments)}")
    print(f"JSON manifest      : {OUTPUT_JSON}")
    print(f"Text summary       : {OUTPUT_TXT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
