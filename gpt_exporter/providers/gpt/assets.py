"""GPT-specific asset classification built on the shared archive taxonomy."""

from __future__ import annotations

import json
import lzma
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gpt_exporter.assets import ASSET_BUCKETS, asset_bucket, asset_bucket_path, move_verified


_ASSET_ID_RE = re.compile(r"(file(?:_|-)[A-Za-z0-9]+|external_[A-Za-z0-9]+)")
_REGISTRY_NAME = "asset-download-index-v2.json.xz"


@dataclass(frozen=True, slots=True)
class GptAssetLayoutMigrationResult:
    moved: int
    reused: int
    unchanged: int
    missing: int
    registry_updated: bool
    affected_conversations: tuple[str, ...] = ()


def _load_json(path: Path) -> Any:
    if path.name.casefold().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_xz_verified(path: Path, payload: Any) -> None:
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    try:
        with lzma.open(temporary, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(raw)
        with lzma.open(temporary, "rb") as handle:
            if handle.read() != raw:
                raise RuntimeError(f"XZ verification failed: {path}")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _extract_asset_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _ASSET_ID_RE.search(value)
    return match.group(1) if match else None


def _conversation_files(downloads: Path) -> list[Path]:
    files = sorted(downloads.glob("*.json.xz"))
    if files:
        return files
    return sorted(
        path for path in downloads.glob("*.json")
        if path.name != "download-index.json"
    )


def _semantic_asset_layout(
    downloads: Path,
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Infer asset buckets and the conversations referencing each asset ID."""
    buckets: dict[str, str] = {}
    references: dict[str, set[str]] = {}
    precedence = {"attachment": 1, "image": 2, "dictation": 3, "external": 4}

    for path in _conversation_files(downloads):
        try:
            payload = _load_json(path)
        except (OSError, EOFError, lzma.LZMAError, UnicodeError, json.JSONDecodeError):
            continue

        referenced_ids: set[str] = set()

        def assign(asset_id: str | None, bucket: str) -> None:
            if asset_id is None:
                return
            referenced_ids.add(asset_id)
            current = buckets.get(asset_id)
            if current is None or precedence[bucket] > precedence[current]:
                buckets[asset_id] = bucket

        def walk(value: object) -> None:
            if isinstance(value, dict):
                content_type = value.get("content_type")
                if content_type == "image_asset_pointer":
                    assign(_extract_asset_id(value.get("asset_pointer")), "image")

                metadata = value.get("metadata")
                if isinstance(metadata, dict):
                    assign(_extract_asset_id(metadata.get("dictation_asset_pointer")), "dictation")

                    attachments = metadata.get("attachments")
                    if isinstance(attachments, list):
                        for attachment in attachments:
                            if not isinstance(attachment, dict):
                                continue
                            for key in (
                                "id",
                                "file_id",
                                "library_file_id",
                                "asset_pointer",
                                "pointer",
                                "download_url",
                                "url",
                            ):
                                assign(_extract_asset_id(attachment.get(key)), "attachment")

                    external_images = metadata.get("_archive_external_images")
                    if isinstance(external_images, list):
                        for external in external_images:
                            if isinstance(external, dict):
                                assign(_extract_asset_id(external.get("asset_id")), "external")

                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(payload)
        for asset_id in referenced_ids:
            references.setdefault(asset_id, set()).add(path.name)

    return buckets, references


def _record_bucket(record: dict[str, Any], semantic: dict[str, str]) -> str:
    file_id = str(record.get("file_id") or "")
    if file_id in semantic:
        return semantic[file_id]
    kind = str(record.get("kind") or "")
    if file_id.startswith("external_") or kind.casefold() == "external_image":
        return "external"
    return asset_bucket(kind, record.get("content_type"))


def migrate_gpt_asset_layout(archive_root: Path | str) -> GptAssetLayoutMigrationResult:
    """Move GPT assets into canonical buckets and repair registry paths safely."""
    root = Path(archive_root).expanduser().resolve()
    assets = root / "assets"
    downloads = root / "downloads"
    reports = root / "reports"
    for bucket in ASSET_BUCKETS:
        asset_bucket_path(assets, bucket).mkdir(parents=True, exist_ok=True)

    registry_path = reports / _REGISTRY_NAME
    legacy_registry = reports / _REGISTRY_NAME.removesuffix(".xz")
    source_registry = registry_path if registry_path.is_file() else legacy_registry
    if not source_registry.is_file():
        return GptAssetLayoutMigrationResult(0, 0, 0, 0, False)

    payload = _load_json(source_registry)
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError(f"Invalid GPT asset registry: {source_registry}")

    semantic, references = _semantic_asset_layout(downloads)
    moved = reused = unchanged = missing = 0
    changed = False
    changed_asset_ids: set[str] = set()

    for record in payload["results"]:
        if not isinstance(record, dict) or record.get("status") not in {"downloaded", "skipped"}:
            continue
        filename = record.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            continue

        file_id = str(record.get("file_id") or "")
        relative = Path(filename.replace("\\", "/"))
        source = assets / relative
        bucket = _record_bucket(record, semantic)
        destination = asset_bucket_path(assets, bucket) / relative.name
        desired_relative = destination.relative_to(assets).as_posix()

        if source.resolve() == destination.resolve():
            unchanged += 1
            continue
        if not source.is_file():
            # A previous run may already have moved the file while the registry
            # update was interrupted. Recover by checking the canonical target.
            if destination.is_file():
                record["filename"] = desired_relative
                changed = True
                if file_id:
                    changed_asset_ids.add(file_id)
                reused += 1
            else:
                missing += 1
            continue

        destination_existed = destination.exists()
        move_verified(source, destination)
        record["filename"] = desired_relative
        changed = True
        if file_id:
            changed_asset_ids.add(file_id)
        if destination_existed:
            reused += 1
        else:
            moved += 1

    if changed or source_registry != registry_path:
        reports.mkdir(parents=True, exist_ok=True)
        _write_xz_verified(registry_path, payload)
        if legacy_registry.is_file():
            legacy_registry.unlink()

    affected_conversations = tuple(
        sorted(
            {
                conversation_name
                for asset_id in changed_asset_ids
                for conversation_name in references.get(asset_id, ())
            }
        )
    )

    return GptAssetLayoutMigrationResult(
        moved=moved,
        reused=reused,
        unchanged=unchanged,
        missing=missing,
        registry_updated=changed or source_registry != registry_path,
        affected_conversations=affected_conversations,
    )


__all__ = ["GptAssetLayoutMigrationResult", "migrate_gpt_asset_layout"]
