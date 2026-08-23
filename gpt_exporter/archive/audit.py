"""Asset-reference audit library for GPT Exporter archives.

The module is side-effect free at import time. It exposes the v2.8/v2.7-audit
analysis helpers as reusable functions and separates report collection from
persistence so the GUI, CLI, tests, and future pipeline can share one engine.
"""

from __future__ import annotations

import hashlib
import json
import lzma
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree


DEFAULT_REPORT_NAME = "asset-reference-audit-v2.7.json.xz"
AUDIT_VERSION = "v2.7"
SCHEMA_VERSION = 2

LOCAL_ASSET_ID_PATTERN = re.compile(
    r"^(file(?:_|-)[A-Za-z0-9]+|external_[A-Za-z0-9]+)"
)
ASSET_ID_ANY_PATTERN = re.compile(
    r"(file(?:_|-)[A-Za-z0-9]+|external_[A-Za-z0-9]+)"
)
ASSET_REFERENCE_PATTERN = re.compile(
    r"Asset\s+ID:\s*`?\s*"
    r"(file(?:_|-)[A-Za-z0-9]+|external_[A-Za-z0-9]+)",
    flags=re.IGNORECASE,
)
SKIP_SUFFIXES = {".failed", ".part", ".headers"}


class ArchiveRootNotFoundError(FileNotFoundError):
    """Raised when the requested archive root does not exist."""


@dataclass(frozen=True, slots=True)
class AssetAuditResult:
    """Structured result of one cumulative asset-reference audit."""

    archive_root: Path
    report: dict[str, object]
    report_path: Path


def local_asset_id(path: Path) -> str | None:
    if path.suffix.lower() in SKIP_SUFFIXES:
        return None
    if path.stat().st_size <= 0:
        return None
    match = LOCAL_ASSET_ID_PATTERN.match(path.name)
    return match.group(1) if match is not None else None


def collect_local_assets(
    asset_root: Path,
) -> tuple[dict[str, list[str]], int, list[str]]:
    by_id: dict[str, list[str]] = defaultdict(list)
    unidentified: list[str] = []
    scanned = 0

    if not asset_root.is_dir():
        return {}, scanned, unidentified

    for path in asset_root.rglob("*"):
        if not path.is_file():
            continue
        scanned += 1
        if path.suffix.lower() in SKIP_SUFFIXES or path.stat().st_size <= 0:
            continue
        relative = path.relative_to(asset_root.parent).as_posix()
        file_id = local_asset_id(path)
        if file_id is None:
            unidentified.append(relative)
            continue
        by_id[file_id].append(relative)

    return dict(by_id), scanned, sorted(unidentified)


def markdown_asset_references(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    references = set(ASSET_REFERENCE_PATTERN.findall(text))

    # Also count local archive links such as:
    #   [file](../assets/attachment/file_xxx__name.ext)
    # and file:// targets created by downstream tooling.
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        target = match.group(1)
        if "assets/" not in target.replace("\\", "/"):
            continue
        references.update(ASSET_ID_ANY_PATTERN.findall(target))

    return references


def paragraph_texts_from_xml(xml_bytes: bytes) -> Iterable[str]:
    root = ElementTree.fromstring(xml_bytes)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    text_tag = f"{namespace}t"
    break_tags = {
        f"{namespace}br",
        f"{namespace}cr",
        f"{namespace}tab",
    }

    for paragraph in root.iter(f"{namespace}p"):
        parts: list[str] = []
        for element in paragraph.iter():
            if element.tag == text_tag:
                parts.append(element.text or "")
            elif element.tag in break_tags:
                parts.append("\n")
        yield "".join(parts)


def docx_asset_references(path: Path) -> set[str]:
    references: set[str] = set()

    with zipfile.ZipFile(path, "r") as archive:
        for member in archive.namelist():
            if not member.startswith("word/") or not member.endswith(".xml"):
                continue
            try:
                xml_bytes = archive.read(member)
                for paragraph_text in paragraph_texts_from_xml(xml_bytes):
                    references.update(
                        ASSET_REFERENCE_PATTERN.findall(paragraph_text)
                    )
            except ElementTree.ParseError:
                continue

        # Hyperlinks to local archived assets live in OOXML relationship
        # files and do not necessarily have a visible "Asset ID:" marker.
        # Count those targets as real rendered references as well.
        for member in archive.namelist():
            if not member.startswith("word/_rels/") or not member.endswith(".rels"):
                continue
            try:
                root = ElementTree.fromstring(archive.read(member))
            except ElementTree.ParseError:
                continue
            for relationship in root:
                target = relationship.attrib.get("Target")
                if not isinstance(target, str):
                    continue
                normalized = target.replace("\\", "/")
                if "assets/" not in normalized:
                    continue
                references.update(ASSET_ID_ANY_PATTERN.findall(target))

    return references


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duplicate_kind(paths: list[str]) -> str:
    buckets = []
    for relative in paths:
        parts = Path(relative).parts
        buckets.append(parts[1].lower() if len(parts) > 1 else "")
    bucket_set = set(buckets)
    if bucket_set == {"attachment", "dictation"}:
        return "dictation_mirror"
    if bucket_set == {"attachment", "image"}:
        return "image_mirror"
    if bucket_set == {"attachment"}:
        return "attachment_filename_variant"
    return "other"


def describe_duplicate(
    archive_root: Path,
    file_id: str,
    paths: list[str],
) -> dict[str, object]:
    sizes: dict[str, int | None] = {}
    digests: dict[str, str | None] = {}
    unreadable = False

    for relative in sorted(paths):
        full_path = archive_root / Path(relative)
        try:
            sizes[relative] = full_path.stat().st_size
            digests[relative] = sha256_file(full_path)
        except OSError:
            sizes[relative] = None
            digests[relative] = None
            unreadable = True

    known_digests = {value for value in digests.values() if value is not None}
    if unreadable:
        content_status = "unreadable"
    elif len(known_digests) == 1:
        content_status = "identical"
    else:
        content_status = "conflicting"

    return {
        "file_id": file_id,
        "paths": sorted(paths),
        "kind": duplicate_kind(paths),
        "content_status": content_status,
        "sizes": sizes,
        "sha256": digests,
    }


def scan_outputs(
    archive_root: Path,
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    referenced_by: dict[str, list[str]] = defaultdict(list)
    docx_files = sorted(archive_root.glob("*.docx"))
    markdown_root = archive_root / "markdown"
    markdown_files = (
        sorted(markdown_root.glob("*.md"))
        if markdown_root.is_dir()
        else []
    )

    for path in docx_files:
        for file_id in docx_asset_references(path):
            referenced_by[file_id].append(path.name)

    for path in markdown_files:
        for file_id in markdown_asset_references(path):
            referenced_by[file_id].append(
                str(path.relative_to(archive_root))
            )

    return (
        dict(referenced_by),
        [path.name for path in docx_files],
        [str(path.relative_to(archive_root)) for path in markdown_files],
    )


def extract_ids_from_value(value: object) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, str):
        ids.update(ASSET_ID_ANY_PATTERN.findall(value))
        return ids
    if isinstance(value, list):
        for item in value:
            ids.update(extract_ids_from_value(item))
        return ids
    if isinstance(value, dict):
        for item in value.values():
            ids.update(extract_ids_from_value(item))
    return ids


def active_node_ids(conversation: dict[str, object]) -> set[str]:
    mapping = conversation.get("mapping")
    current = conversation.get("current_node")
    if not isinstance(mapping, dict) or not isinstance(current, str):
        return set()
    output: set[str] = set()
    seen: set[str] = set()
    node_id: str | None = current
    while isinstance(node_id, str) and node_id and node_id not in seen:
        seen.add(node_id)
        output.add(node_id)
        node = mapping.get(node_id)
        if not isinstance(node, dict):
            break
        parent = node.get("parent")
        node_id = parent if isinstance(parent, str) else None
    return output


def collect_archive_occurrences(
    archive_root: Path,
) -> dict[str, list[dict[str, object]]]:
    occurrences: dict[str, list[dict[str, object]]] = defaultdict(list)
    downloads = archive_root / "downloads"
    if not downloads.is_dir():
        return {}

    for path in sorted(downloads.glob("*.json.xz")):
        try:
            with lzma.open(path, "rt", encoding="utf-8") as handle:
                conversation = json.load(handle)
        except (OSError, lzma.LZMAError, json.JSONDecodeError):
            continue
        if not isinstance(conversation, dict):
            continue
        mapping = conversation.get("mapping")
        if not isinstance(mapping, dict):
            continue
        active = active_node_ids(conversation)
        title = conversation.get("title")
        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue
            message = node.get("message")
            if not isinstance(message, dict):
                continue
            author = message.get("author")
            role = author.get("role") if isinstance(author, dict) else None
            content = message.get("content")
            content_type = (
                content.get("content_type")
                if isinstance(content, dict)
                else None
            )
            metadata = message.get("metadata")
            hidden = (
                bool(metadata.get("is_visually_hidden_from_conversation"))
                if isinstance(metadata, dict)
                else False
            )
            base = {
                "conversation": path.name,
                "title": title,
                "node_id": str(node_id),
                "active": str(node_id) in active,
                "hidden": hidden,
                "role": role,
                "tool_name": (
                    author.get("name") if isinstance(author, dict) else None
                ),
                "content_type": content_type,
            }

            if isinstance(metadata, dict):
                pointer = metadata.get("dictation_asset_pointer")
                for file_id in extract_ids_from_value(pointer):
                    occurrences[file_id].append(
                        {**base, "location": "dictation_asset_pointer"}
                    )
                attachments = metadata.get("attachments")
                if isinstance(attachments, list):
                    for attachment in attachments:
                        if not isinstance(attachment, dict):
                            continue
                        raw_id = attachment.get("id") or attachment.get("file_id")
                        for file_id in extract_ids_from_value(raw_id):
                            occurrences[file_id].append(
                                {**base, "location": "metadata.attachments"}
                            )

                # Source/citation metadata is intentionally diagnostic only;
                # it must not cause an asset to be rendered in a DOCX.
                for key in ("content_references", "search_result_groups"):
                    if key in metadata:
                        for file_id in extract_ids_from_value(metadata.get(key)):
                            occurrences[file_id].append(
                                {**base, "location": f"metadata.{key}"}
                            )

            if isinstance(content, dict):
                for file_id in extract_ids_from_value(content):
                    occurrences[file_id].append(
                        {**base, "location": "content"}
                    )

    return dict(occurrences)


def classify_unreferenced(
    unreferenced_ids: list[str],
    occurrences: dict[str, list[dict[str, object]]],
) -> tuple[dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    categories: dict[str, list[dict[str, object]]] = defaultdict(list)
    details: list[dict[str, object]] = []
    for file_id in unreferenced_ids:
        refs = occurrences.get(file_id, [])
        dictation_refs = [
            ref
            for ref in refs
            if ref.get("location") == "dictation_asset_pointer"
        ]
        if any(
            bool(ref.get("active")) and not bool(ref.get("hidden"))
            for ref in dictation_refs
        ):
            category = "dictation_source_active"
        elif dictation_refs:
            category = "dictation_source_inactive_or_hidden"
        elif refs and not any(bool(ref.get("active")) for ref in refs):
            category = "inactive_branch_only"
        elif any(
            bool(ref.get("active"))
            and ref.get("role") == "tool"
            and ref.get("tool_name") == "container.open_image"
            and ref.get("content_type") == "execution_output"
            and ref.get("location") == "metadata.attachments"
            for ref in refs
        ):
            category = "internal_image_inspection"
        elif any(
            bool(ref.get("active"))
            and ref.get("role") == "tool"
            and ref.get("content_type") == "execution_output"
            and ref.get("location") == "metadata.attachments"
            for ref in refs
        ):
            category = "tool_execution_attachment"
        elif any(
            bool(ref.get("active")) and ref.get("role") == "tool"
            for ref in refs
        ):
            category = "tool_source_or_internal"
        elif any(bool(ref.get("active")) for ref in refs):
            category = "active_unrendered_reference"
        elif refs:
            category = "known_json_reference"
        else:
            category = "unexplained"
        item = {
            "file_id": file_id,
            "category": category,
            "occurrences": refs,
        }
        categories[category].append(item)
        details.append(item)
    return dict(categories), details


def collect_asset_audit(archive_root: Path) -> dict[str, object]:
    """Collect the cumulative v2.8 asset-reference audit report model."""

    archive_root = Path(archive_root).expanduser().resolve()
    if not archive_root.is_dir():
        raise ArchiveRootNotFoundError(f"archive root not found: {archive_root}")

    asset_root = archive_root / "assets"
    local_assets, asset_files_scanned, unidentified_files = collect_local_assets(
        asset_root
    )
    referenced_by, docx_files, markdown_files = scan_outputs(archive_root)

    local_ids = set(local_assets)
    referenced_ids = set(referenced_by)
    unreferenced_ids = sorted(local_ids - referenced_ids)
    missing_local_ids = sorted(referenced_ids - local_ids)

    occurrences = collect_archive_occurrences(archive_root)
    unreferenced_categories, unreferenced_details = classify_unreferenced(
        unreferenced_ids,
        occurrences,
    )

    detail_by_id = {
        item["file_id"]: item
        for item in unreferenced_details
    }
    unreferenced = [
        {
            "file_id": file_id,
            "paths": sorted(local_assets[file_id]),
            "category": detail_by_id[file_id]["category"],
            "occurrences": detail_by_id[file_id]["occurrences"],
        }
        for file_id in unreferenced_ids
    ]
    missing_local = [
        {
            "file_id": file_id,
            "referenced_by": sorted(referenced_by[file_id]),
        }
        for file_id in missing_local_ids
    ]

    duplicates = [
        describe_duplicate(
            archive_root,
            file_id,
            paths,
        )
        for file_id, paths in sorted(local_assets.items())
        if len(paths) > 1
    ]
    duplicate_status_counts = {
        status: sum(
            1
            for item in duplicates
            if item.get("content_status") == status
        )
        for status in ("identical", "conflicting", "unreadable")
    }
    duplicate_kind_counts = {
        kind: sum(
            1
            for item in duplicates
            if item.get("kind") == kind
        )
        for kind in sorted(
            {
                str(item.get("kind"))
                for item in duplicates
            }
        )
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "archive_root": str(archive_root),
        "asset_files_scanned": asset_files_scanned,
        "unique_local_asset_ids": len(local_ids),
        "docx_files_scanned": len(docx_files),
        "markdown_files_scanned": len(markdown_files),
        "referenced_asset_ids": len(referenced_ids),
        "unreferenced_local_asset_count": len(unreferenced),
        "referenced_missing_local_count": len(missing_local),
        "duplicate_local_asset_id_count": len(duplicates),
        "duplicate_local_asset_content_status_counts": duplicate_status_counts,
        "duplicate_local_asset_kind_counts": duplicate_kind_counts,
        "unidentified_local_asset_file_count": len(unidentified_files),
        "unreferenced_local_assets": unreferenced,
        "unreferenced_category_counts": {
            key: len(value)
            for key, value in sorted(unreferenced_categories.items())
        },
        "referenced_missing_local_assets": missing_local,
        "duplicate_local_asset_ids": duplicates,
        "unidentified_local_asset_files": unidentified_files,
    }


def write_asset_audit_report(
    report_path: Path,
    report: dict[str, object],
) -> None:
    """Persist one compressed asset-reference audit report."""

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with lzma.open(report_path, "wt", encoding="utf-8", preset=6) as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def audit_asset_references(archive_root: Path) -> AssetAuditResult:
    """Collect and persist the cumulative asset-reference audit."""

    resolved_root = Path(archive_root).expanduser().resolve()
    report = collect_asset_audit(resolved_root)
    report_path = resolved_root / "reports" / DEFAULT_REPORT_NAME
    write_asset_audit_report(report_path, report)
    return AssetAuditResult(
        archive_root=resolved_root,
        report=report,
        report_path=report_path,
    )


# Compatibility alias for callers of the historical script helper.
write_report = write_asset_audit_report
