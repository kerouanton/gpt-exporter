"""Asset manifest library for GPT Exporter archives.

The module is side-effect free at import time. It separates collection,
formatting, and persistence so callers can use the manifest logic without
invoking a CLI script or another Python process.
"""

from __future__ import annotations

import json
import lzma
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


JSON_MANIFEST_NAME = "asset-manifest.json.xz"
TEXT_MANIFEST_NAME = "asset-manifest.txt"
LEGACY_JSON_MANIFEST_NAME = "asset-manifest.json"

ProgressCallback = Callable[[str], None]


class NoConversationFilesError(FileNotFoundError):
    """Raised when no archived conversation JSON files are available."""


@dataclass(frozen=True, slots=True)
class AssetManifestResult:
    """Structured result of one asset-manifest run."""

    manifest: dict[str, object]
    json_manifest_path: Path
    text_manifest_path: Path


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    """Yield every nested dictionary in a JSON-like value."""

    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def add_unique(
    items: dict[str, dict[str, Any]],
    key: str,
    record: dict[str, Any],
) -> None:
    """Store the first record observed for a logical asset key."""

    if key not in items:
        items[key] = record


def conversation_files(downloads_dir: Path) -> list[Path]:
    """Return conversation files using the unchanged v2.8 fallback order."""

    downloads_dir = Path(downloads_dir)
    files = sorted(downloads_dir.glob("*.json.xz"))
    if not files:
        files = sorted(
            path
            for path in downloads_dir.glob("*.json")
            if path.name != "download-index.json"
        )
    return files


def _load_conversation(path: Path) -> dict[str, Any]:
    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise ValueError(f"Conversation root is not a JSON object: {path}")
    return data


def collect_asset_manifest(
    downloads_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    """Collect the v2.8 asset manifest model from archived conversations."""

    files = conversation_files(downloads_dir)
    if not files:
        raise NoConversationFilesError(
            f"No conversation JSON files found in: {Path(downloads_dir)}"
        )

    images: dict[str, dict[str, Any]] = {}
    dictations: dict[str, dict[str, Any]] = {}
    attachments: dict[str, dict[str, Any]] = {}
    raw_counts: Counter[str] = Counter()

    for index, path in enumerate(files, start=1):
        if progress is not None:
            progress(f"[{index}/{len(files)}] {path.name}")

        data = _load_conversation(path)
        conversation_id = data.get("conversation_id")
        title = data.get("title")
        mapping = data.get("mapping", {})

        if not isinstance(mapping, dict):
            continue

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

    extensions: Counter[str] = Counter()
    for item in attachments.values():
        name = item.get("name")
        if isinstance(name, str):
            suffix = Path(name).suffix.lower()
            if suffix:
                extensions[suffix] += 1

    return {
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
            sorted(mime_types.items(), key=lambda item: (-item[1], item[0]))
        ),
        "attachment_extensions": dict(
            sorted(extensions.items(), key=lambda item: (-item[1], item[0]))
        ),
        "images": list(images.values()),
        "dictations": list(dictations.values()),
        "attachments": list(attachments.values()),
    }


def render_text_manifest(manifest: dict[str, object]) -> str:
    """Render the v2.8 human-readable manifest summary."""

    summary = manifest.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    mime_types = manifest.get("attachment_mime_types", {})
    if not isinstance(mime_types, dict):
        mime_types = {}
    extensions = manifest.get("attachment_extensions", {})
    if not isinstance(extensions, dict):
        extensions = {}

    lines = [
        "ChatGPT Asset Manifest",
        "======================",
        "",
        f"Conversation files             : {summary.get('conversation_files', 0)}",
        f"Unique images                  : {summary.get('unique_images', 0)}",
        f"Unique dictations              : {summary.get('unique_dictations', 0)}",
        f"Unique attachments             : {summary.get('unique_attachments', 0)}",
        "Raw image pointer occurrences  : "
        f"{summary.get('raw_image_pointer_occurrences', 0)}",
        "Raw dictation occurrences      : "
        f"{summary.get('raw_dictation_pointer_occurrences', 0)}",
        "Raw attachment occurrences     : "
        f"{summary.get('raw_attachment_occurrences', 0)}",
        "",
        "Attachment MIME types",
        "---------------------",
    ]

    for key, count in sorted(
        mime_types.items(),
        key=lambda item: (-int(item[1]), str(item[0])),
    ):
        lines.append(f"{key}: {count}")

    lines.extend(["", "Attachment extensions", "---------------------"])
    for key, count in sorted(
        extensions.items(),
        key=lambda item: (-int(item[1]), str(item[0])),
    ):
        lines.append(f"{key}: {count}")

    return "\n".join(lines) + "\n"


def write_asset_manifest(
    manifest: dict[str, object],
    reports_dir: Path,
) -> tuple[Path, Path]:
    """Write verified compressed JSON and text manifest outputs."""

    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / JSON_MANIFEST_NAME
    text_path = reports_dir / TEXT_MANIFEST_NAME

    manifest_raw = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    temp_json = json_path.with_name(json_path.name + ".tmp")
    try:
        with lzma.open(
            temp_json,
            "wb",
            format=lzma.FORMAT_XZ,
            preset=6,
        ) as handle:
            handle.write(manifest_raw)
        with lzma.open(temp_json, "rb") as handle:
            if handle.read() != manifest_raw:
                raise RuntimeError(f"XZ verification failed: {json_path}")
        temp_json.replace(json_path)
    finally:
        if temp_json.exists():
            temp_json.unlink()

    legacy_json = reports_dir / LEGACY_JSON_MANIFEST_NAME
    if legacy_json.is_file():
        legacy_json.unlink()

    text_path.write_text(render_text_manifest(manifest), encoding="utf-8")
    return json_path, text_path


def build_asset_manifest(
    downloads_dir: Path,
    reports_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> AssetManifestResult:
    """Collect and persist one asset-manifest run."""

    reports_dir = Path(reports_dir)
    # v2.8 creates the reports directory before checking for input files.
    reports_dir.mkdir(parents=True, exist_ok=True)
    manifest = collect_asset_manifest(downloads_dir, progress=progress)
    json_path, text_path = write_asset_manifest(manifest, reports_dir)
    return AssetManifestResult(
        manifest=manifest,
        json_manifest_path=json_path,
        text_manifest_path=text_path,
    )


def render_console_summary(result: AssetManifestResult) -> str:
    """Render the v2.8 terminal summary without printing it."""

    summary = result.manifest.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return "\n".join(
        [
            "Asset manifest complete",
            "=======================",
            f"Unique images      : {summary.get('unique_images', 0)}",
            f"Unique dictations  : {summary.get('unique_dictations', 0)}",
            f"Unique attachments : {summary.get('unique_attachments', 0)}",
            f"JSON manifest      : {result.json_manifest_path}",
            f"Text summary       : {result.text_manifest_path}",
        ]
    )
