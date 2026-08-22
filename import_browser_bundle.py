import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import base64
import hashlib
import json
import lzma
import mimetypes
import re
import ssl
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
DOWNLOADS_DIR = ARCHIVE_ROOT / "downloads"
ASSETS_DIR = ARCHIVE_ROOT / "assets"
REPORTS_DIR = ARCHIVE_ROOT / "reports"
DEFAULT_BUNDLE = USER_PROFILE / "Downloads" / "chatgpt-archive-source.json"
DEBUG = True
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
    "Gecko/20100101 Firefox/140.0"
)
MAX_EXTERNAL_IMAGE_BYTES = 30 * 1024 * 1024


def debug(message: str) -> None:
    if DEBUG:
        print(f"DEBUG: {message}")


def remove_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def sanitize_filename(text: str) -> str:
    text = remove_accents(text)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text[:120] or "Untitled conversation"


def date_prefix(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date().isoformat()
    if isinstance(value, str):
        match = re.match(r"^\d{4}-\d{2}-\d{2}", value)
        if match:
            return match.group(0)
    return "unknown-date"


def extension_for(content_type: str | None, url: str | None = None) -> str:
    if content_type:
        clean = content_type.split(";", 1)[0].strip().lower()
        special = {
            "image/jpeg": ".jpg",
            "image/svg+xml": ".svg",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }
        guessed = special.get(clean) or mimetypes.guess_extension(clean)
        if guessed:
            return guessed
    if url:
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if re.fullmatch(r"\.(?:avif|bmp|gif|jpe?g|png|svg|webp)", suffix):
            return suffix
    return ".bin"


def normalize_external_urls(asset: dict[str, Any]) -> list[str]:
    values: list[str] = []
    candidate_urls = asset.get("candidate_urls")
    if isinstance(candidate_urls, list):
        values.extend(value for value in candidate_urls if isinstance(value, str))
    source_url = asset.get("source_url")
    if isinstance(source_url, str):
        values.insert(0, source_url)
    result: list[str] = []
    for value in values:
        if value.startswith(("http://", "https://")) and value not in result:
            result.append(value)
    return result


def classify_asset_error(error: str | None) -> str:
    text = str(error or "")
    if re.search(r"\b404\b", text):
        return "http_404"
    if re.search(r"\b403\b", text):
        return "http_403"
    if "JSON download descriptor contains no URL" in text:
        return "descriptor_no_url"
    if "Browser cache says downloaded" in text:
        return "local_missing"
    return "other"


def read_json_document(path: Path) -> Any:
    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_xz_verified(path: Path, raw: bytes) -> None:
    temp = path.with_name(path.name + ".tmp")
    try:
        with lzma.open(temp, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(raw)
        with lzma.open(temp, "rb") as handle:
            verified = handle.read()
        if verified != raw:
            raise RuntimeError(f"XZ verification failed: {path}")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def uncompressed_size(path: Path) -> int:
    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rb") as handle:
            return len(handle.read())
    return path.stat().st_size


def load_asset_registry(path: Path) -> dict[str, dict[str, Any]]:
    candidates = [path]
    if path.name.lower().endswith(".json.xz"):
        candidates.append(path.with_name(path.name[:-3]))
    source = next((candidate for candidate in candidates if candidate.is_file()), None)
    if source is None:
        return {}
    try:
        payload = read_json_document(source)
    except (OSError, EOFError, lzma.LZMAError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"WARNING: Unable to read previous asset registry: {exc}")
        return {}

    registry: dict[str, dict[str, Any]] = {}
    for item in payload.get("results", []):
        if not isinstance(item, dict):
            continue
        file_id = item.get("file_id")
        if isinstance(file_id, str):
            registry[file_id] = dict(item)
    return registry


def find_local_asset(
    file_id: str,
    prior: dict[str, Any] | None,
) -> tuple[Path | None, str | None]:
    if isinstance(prior, dict):
        filename = prior.get("filename")
        if isinstance(filename, str) and filename:
            candidate = ASSETS_DIR / filename
            if candidate.is_file():
                return candidate, filename.replace("\\", "/")

    attachment_dir = ASSETS_DIR / "attachment"
    matches = sorted(path for path in attachment_dir.glob(f"{file_id}*") if path.is_file())
    if not matches:
        return None, None
    candidate = matches[0]
    return candidate, str(candidate.relative_to(ASSETS_DIR)).replace("\\", "/")


def downloaded_record_from_local(
    file_id: str,
    path: Path,
    relative: str,
    prior: dict[str, Any] | None,
    now: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    record = dict(prior or {})
    record.update({
        "kind": record.get("kind") or "attachment",
        "file_id": file_id,
        "status": "downloaded",
        "filename": relative,
        "size_bytes": len(raw),
        "content_type": record.get("content_type"),
        "source_url": record.get("source_url"),
        "title": record.get("title"),
        "attribution": record.get("attribution"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "error": None,
        "failure_class": None,
        "last_seen": now,
        "cache_hit": True,
    })
    record.setdefault("first_seen", now)
    record.setdefault("attempt_count", 1 if prior else 0)
    return record


def download_external_image(asset: dict[str, Any]) -> tuple[bytes, str, str]:
    errors: list[str] = []
    context = ssl.create_default_context()
    source_page = asset.get("source_page")

    for url in normalize_external_urls(asset):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.7",
        }
        if isinstance(source_page, str) and source_page.startswith(("http://", "https://")):
            headers["Referer"] = source_page
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            debug(f"Downloading external image: {url}")
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                content_type = response.headers.get_content_type() or "application/octet-stream"
                if not content_type.lower().startswith("image/"):
                    raise ValueError(f"Response is not an image: {content_type}")
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > MAX_EXTERNAL_IMAGE_BYTES:
                    raise ValueError(f"Image is too large: {declared} bytes")
                raw = response.read(MAX_EXTERNAL_IMAGE_BYTES + 1)
                if len(raw) > MAX_EXTERNAL_IMAGE_BYTES:
                    raise ValueError("Image exceeds the 30 MiB limit")
                if not raw:
                    raise ValueError("Empty response")
                return raw, content_type, response.geturl()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError(" | ".join(errors) or "No usable external image URL")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a browser-generated ChatGPT archive source bundle."
    )
    parser.add_argument(
        "bundle", nargs="?", type=Path, default=DEFAULT_BUNDLE
    )
    args = parser.parse_args()

    bundle_path = args.bundle.resolve()
    if not bundle_path.is_file():
        raise FileNotFoundError(f"Browser bundle not found: {bundle_path}")

    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    if data.get("format") != "chatgpt-archive-source-v1":
        raise ValueError("Unsupported or invalid browser bundle format.")

    downloads = DOWNLOADS_DIR
    assets_dir = ASSETS_DIR / "attachment"
    reports = REPORTS_DIR
    downloads.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    registry_path = reports / "asset-download-index-v2.json.xz"
    registry = load_asset_registry(registry_path)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    conversations = data.get("conversations", [])
    written_conversations = 0
    preserved_conversations = 0
    current_batch: list[str] = []
    for conversation in conversations:
        if not isinstance(conversation, dict):
            continue
        conversation_id = conversation.get("conversation_id")
        if not isinstance(conversation_id, str):
            continue
        title = sanitize_filename(str(conversation.get("title") or "Untitled conversation"))
        prefix = date_prefix(conversation.get("create_time"))
        rendered = (
            json.dumps(conversation, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

        existing_xz = sorted(downloads.glob(f"*_{conversation_id}.json.xz"))
        existing_json = sorted(downloads.glob(f"*_{conversation_id}.json"))
        if existing_xz and existing_json:
            raise RuntimeError(
                "Both compressed and uncompressed conversation files exist for "
                f"{conversation_id}. Run archive_chats.py once to migrate safely."
            )
        existing_matches = existing_xz or existing_json
        if existing_matches:
            existing = existing_matches[0]
            if existing.name.lower().endswith(".json.xz"):
                output = existing
            else:
                output = existing.with_name(existing.name + ".xz")
        else:
            output = downloads / f"{prefix}_{title}_{conversation_id}.json.xz"

        existing_size = uncompressed_size(existing_matches[0]) if existing_matches else -1
        new_size = len(rendered)

        if existing_size >= new_size:
            preserved_conversations += 1
            print(
                "Preserved conversation: "
                f"{conversation_id} "
                f"(stored={existing_size}, incoming={new_size})"
            )
            continue

        write_xz_verified(output, rendered)
        for legacy in existing_matches:
            if legacy != output and legacy.suffix.lower() == ".json":
                legacy.unlink()
        current_batch.append(output.name)
        written_conversations += 1
        print(
            "Imported conversation: "
            f"{conversation_id} "
            f"(stored={max(existing_size, 0)}, incoming={new_size})"
        )

    current_results: list[dict[str, Any]] = []
    imported_assets = 0
    reused_assets = 0
    cached_failures = 0
    cache_mismatches = 0
    failed_attempts = 0
    external_images_downloaded = 0

    for asset in data.get("assets", []):
        if not isinstance(asset, dict):
            continue
        file_id = asset.get("file_id")
        status = asset.get("status")
        kind = str(asset.get("kind") or "attachment")
        if not isinstance(file_id, str):
            continue

        prior = registry.get(file_id)
        raw: bytes | None = None
        content_type = asset.get("content_type")
        source_url = asset.get("source_url")
        error: str | None = None

        if status == "cached_downloaded":
            local_path, relative = find_local_asset(file_id, prior)
            if local_path is not None and relative is not None:
                record = downloaded_record_from_local(
                    file_id=file_id,
                    path=local_path,
                    relative=relative,
                    prior=prior,
                    now=now,
                )
                registry[file_id] = record
                current_results.append(record)
                reused_assets += 1
                print(f"Reused cached asset: {file_id} -> {relative}")
                continue

            error = (
                "Browser cache says downloaded, but no matching local asset exists. "
                "Clear or forget this file_id in the browser asset cache before retrying."
            )
            record = dict(prior or {})
            record.update({
                "kind": kind,
                "file_id": file_id,
                "status": "failed",
                "filename": None,
                "size_bytes": None,
                "content_type": content_type,
                "source_url": source_url,
                "title": asset.get("title"),
                "attribution": asset.get("attribution"),
                "error": error,
                "failure_class": "local_missing",
                "last_seen": now,
                "cache_hit": True,
            })
            record.setdefault("first_seen", now)
            record.setdefault("attempt_count", 0)
            registry[file_id] = record
            current_results.append(record)
            cached_failures += 1
            cache_mismatches += 1
            print(f"WARNING: Asset cache mismatch: {file_id}: {error}")
            continue

        if status == "cached_failed":
            record = dict(prior or {})
            cached_error = str(asset.get("error") or record.get("error") or "Previously failed asset")
            record.update({
                "kind": kind,
                "file_id": file_id,
                "status": "failed",
                "filename": record.get("filename"),
                "size_bytes": record.get("size_bytes"),
                "content_type": record.get("content_type") or content_type,
                "source_url": record.get("source_url") or source_url,
                "title": record.get("title") or asset.get("title"),
                "attribution": record.get("attribution") or asset.get("attribution"),
                "error": cached_error,
                "failure_class": asset.get("failure_class") or record.get("failure_class") or classify_asset_error(cached_error),
                "last_seen": now,
                "cache_hit": True,
            })
            record.setdefault("first_seen", now)
            record.setdefault("attempt_count", 1 if prior else 0)
            registry[file_id] = record
            current_results.append(record)
            cached_failures += 1
            continue

        if status == "downloaded" and isinstance(asset.get("base64"), str):
            try:
                raw = base64.b64decode(asset["base64"], validate=True)
            except (ValueError, TypeError) as exc:
                error = f"Invalid Base64 data: {exc}"
        elif kind == "external_image" and status in {
            "pending_external_download",
            "failed",
        }:
            local_path, relative = find_local_asset(file_id, prior)
            if prior and prior.get("status") == "downloaded" and local_path and relative:
                record = downloaded_record_from_local(
                    file_id=file_id,
                    path=local_path,
                    relative=relative,
                    prior=prior,
                    now=now,
                )
                registry[file_id] = record
                current_results.append(record)
                reused_assets += 1
                print(f"Reused external image: {file_id} -> {relative}")
                continue
            try:
                raw, content_type, source_url = download_external_image(asset)
            except RuntimeError as exc:
                error = str(exc)
        else:
            error = str(asset.get("error") or "Not downloaded by browser collector")

        if raw is None:
            attempt_count = int((prior or {}).get("attempt_count") or (1 if prior else 0))
            if status not in {"cached_downloaded", "cached_failed"}:
                attempt_count += 1
                failed_attempts += 1
            record = {
                "kind": kind,
                "file_id": file_id,
                "status": "failed",
                "filename": None,
                "size_bytes": None,
                "content_type": content_type,
                "source_url": source_url,
                "title": asset.get("title"),
                "attribution": asset.get("attribution"),
                "error": error or "Download failed",
                "failure_class": asset.get("failure_class") or classify_asset_error(error),
                "first_seen": (prior or {}).get("first_seen") or now,
                "last_seen": now,
                "last_attempt": now,
                "attempt_count": attempt_count,
                "cache_hit": False,
            }
            registry[file_id] = record
            current_results.append(record)
            print(f"WARNING: Asset failed: {file_id}: {error}")
            continue

        original_name = asset.get("filename")
        if isinstance(original_name, str) and original_name.strip():
            safe_name = sanitize_filename(Path(original_name).name)
            suffix = Path(safe_name).suffix or extension_for(content_type, source_url)
            stem = Path(safe_name).stem
            local_name = f"{file_id}__{stem}{suffix}"
        elif kind == "external_image":
            title = sanitize_filename(str(asset.get("title") or "external-image"))
            local_name = f"{file_id}__{title}{extension_for(content_type, source_url)}"
        else:
            local_name = f"{file_id}{extension_for(content_type, source_url)}"

        output = assets_dir / local_name
        digest = hashlib.sha256(raw).hexdigest()
        if output.is_file() and output.stat().st_size == len(raw):
            try:
                existing_digest = hashlib.sha256(output.read_bytes()).hexdigest()
            except OSError:
                existing_digest = ""
            if existing_digest != digest:
                output.write_bytes(raw)
        else:
            output.write_bytes(raw)
        relative = str(output.relative_to(ASSETS_DIR)).replace("\\", "/")
        attempt_count = int((prior or {}).get("attempt_count") or (1 if prior else 0)) + 1
        record = {
            "kind": kind,
            "file_id": file_id,
            "status": "downloaded",
            "filename": relative,
            "size_bytes": len(raw),
            "content_type": content_type,
            "source_url": source_url,
            "title": asset.get("title"),
            "attribution": asset.get("attribution"),
            "sha256": digest,
            "error": None,
            "failure_class": None,
            "first_seen": (prior or {}).get("first_seen") or now,
            "last_seen": now,
            "last_attempt": now,
            "attempt_count": attempt_count,
            "cache_hit": False,
        }
        registry[file_id] = record
        current_results.append(record)
        imported_assets += 1
        if kind == "external_image":
            external_images_downloaded += 1
        print(f"Imported asset: {file_id} -> {relative}")

    batch_index = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "conversation_files": current_batch,
    }
    (reports / "current-batch.json").write_text(
        json.dumps(batch_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    index = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "registry_mode": "cumulative",
        "results": [registry[file_id] for file_id in sorted(registry)],
    }
    registry_raw = (
        json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    write_xz_verified(registry_path, registry_raw)
    legacy_registry = registry_path.with_name(registry_path.name[:-3])
    if legacy_registry.is_file():
        legacy_registry.unlink()

    print(f"Imported conversations : {written_conversations}")
    print(f"Preserved conversations: {preserved_conversations}")
    print(f"Imported assets        : {imported_assets}")
    print(f"Reused cached assets   : {reused_assets}")
    print(f"Cached failures skipped: {cached_failures}")
    print(f"Cache mismatches        : {cache_mismatches}")
    print(f"Failed asset attempts  : {failed_attempts}")
    print(f"External images fetched: {external_images_downloaded}")
    print(f"Asset registry entries : {len(registry)}")
    if cache_mismatches:
        print()
        print(
            "ERROR: One or more browser-cached downloads are missing from the local archive."
        )
        print(
            "Use gptExporterAssetCache.forget(\"file_id\") in the ChatGPT browser console "
            "for each reported ID (or clear the whole cache), regenerate the browser bundle, "
            "and run archive_chats.py again."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
