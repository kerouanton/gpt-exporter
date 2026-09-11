import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import hashlib
import json
import logging
import lzma
import mimetypes
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


DEBUG = False

DEFAULT_INPUT_FILENAME = "conversation-full.json"
DEFAULT_ASSET_INDEX = "reports/asset-download-index-v2.json.xz"
DEFAULT_ASSET_DIRECTORY = "assets"
DEFAULT_MARKDOWN_DIRECTORY = "markdown"
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
FILE_ID_PATTERN = re.compile(r"(file(?:_|-)[A-Za-z0-9]+)")
LOCAL_ASSET_ID_PATTERN = re.compile(
    r"^(file(?:_|-)[A-Za-z0-9]+|external_[A-Za-z0-9]+)"
)
LOCAL_ASSET_SKIP_SUFFIXES = {".failed", ".part", ".headers"}
LOCAL_CONTENT_TYPE_OVERRIDES = {
    ".m4a": "audio/mp4",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
_LOCAL_ASSET_DISCOVERY_CACHE: dict[str, dict[str, "LocalAsset"]] = {}

VISIBLE_ROLES = {
    "user",
    "assistant",
}

VISIBLE_CONTENT_TYPES = {
    "text",
    "multimodal_text",
    "code",
}


@dataclass
class ExportMessage:
    node_id: str
    role: str
    content_type: str
    text: str
    create_time: Optional[float]
    update_time: Optional[float]


@dataclass
class LocalAsset:
    file_id: str
    kind: str
    filename: str
    content_type: Optional[str]
    size_bytes: Optional[int]


@dataclass
class Conversation:
    title: str
    conversation_id: str
    create_time: Optional[float]
    update_time: Optional[float]
    messages: list[ExportMessage]


@dataclass
class ExportStatistics:
    all_nodes: int = 0
    active_nodes: int = 0
    exported_messages: int = 0
    skipped_reasons: Counter[str] = field(default_factory=Counter)
    roles_in_active_path: Counter[str] = field(default_factory=Counter)
    content_types_in_active_path: Counter[str] = field(
        default_factory=Counter
    )
    cleaned_marker_types: Counter[str] = field(
        default_factory=Counter
    )
    resolved_assets: Counter[str] = field(
        default_factory=Counter
    )
    unresolved_assets: Counter[str] = field(
        default_factory=Counter
    )
    generated_image_tool_messages: int = 0
    generated_image_tool_merges: int = 0


def configure_logging(debug_enabled: bool) -> None:
    level = logging.DEBUG if debug_enabled else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )


def load_json(path: Path) -> dict[str, Any]:
    logging.info("Loading JSON file: %s", path)

    if not path.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"Input path is not a regular file: {path}"
        )

    try:
        if path.name.lower().endswith(".json.xz"):
            with lzma.open(path, "rt", encoding="utf-8") as handle:
                data = json.load(handle)
        else:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

    except (EOFError, lzma.LZMAError) as exc:
        raise ValueError(
            f"The input file is not a valid XZ stream: {path}"
        ) from exc

    except UnicodeDecodeError as exc:
        raise ValueError(
            f"The input file is not valid UTF-8: {path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid JSON at "
            f"line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "The top-level JSON value must be an object."
        )

    mapping = data.get("mapping")

    if not isinstance(mapping, dict):
        raise ValueError(
            "The JSON does not contain a valid 'mapping' object."
        )

    current_node = data.get("current_node")

    if not isinstance(current_node, str):
        raise ValueError(
            "The JSON does not contain a valid "
            "'current_node' identifier."
        )

    logging.info(
        "JSON loaded successfully: %d graph nodes",
        len(mapping),
    )

    return data


def reconstruct_active_path(
    mapping: dict[str, Any],
    current_node_id: str,
) -> list[dict[str, Any]]:
    logging.info(
        "Reconstructing active path from current node: %s",
        current_node_id,
    )

    reversed_path: list[dict[str, Any]] = []
    visited: set[str] = set()

    node_id: Optional[str] = current_node_id

    while node_id is not None:
        if node_id in visited:
            raise ValueError(
                "Cycle detected in the conversation graph "
                f"at node: {node_id}"
            )

        visited.add(node_id)

        node = mapping.get(node_id)

        if not isinstance(node, dict):
            raise ValueError(
                "The active path references a missing or "
                f"invalid node: {node_id}"
            )

        reversed_path.append(node)

        parent_id = node.get("parent")

        if parent_id is not None and not isinstance(
            parent_id,
            str,
        ):
            raise ValueError(
                f"Invalid parent identifier in node {node_id}: "
                f"{parent_id!r}"
            )

        node_id = parent_id

    active_path = list(reversed(reversed_path))

    logging.info(
        "Active path reconstructed: %d nodes",
        len(active_path),
    )

    return active_path


def is_visually_hidden(message: dict[str, Any]) -> bool:
    metadata = message.get("metadata")

    if not isinstance(metadata, dict):
        return False

    return (
        metadata.get(
            "is_visually_hidden_from_conversation"
        )
        is True
    )


def is_visible_generated_image_tool(
    message: dict[str, Any],
) -> bool:
    if is_visually_hidden(message):
        return False

    author = message.get("author")
    if not isinstance(author, dict) or author.get("role") != "tool":
        return False

    content = message.get("content")
    if not isinstance(content, dict):
        return False

    if content.get("content_type") != "multimodal_text":
        return False

    parts = content.get("parts")
    if not isinstance(parts, list):
        return False

    return any(
        isinstance(part, dict)
        and part.get("content_type") == "image_asset_pointer"
        for part in parts
    )


def extract_file_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None

    match = FILE_ID_PATTERN.search(value)

    if match is None:
        return None

    return match.group(1)


def load_asset_index(
    path: Path,
) -> dict[str, LocalAsset]:
    if not path.exists():
        legacy = path.with_name(path.name[:-3]) if path.name.lower().endswith(".json.xz") else None
        if legacy is not None and legacy.exists():
            path = legacy
        else:
            logging.warning(
                "Asset index not found; links will remain unresolved: %s",
                path,
            )
            return {}

    if path.name.lower().endswith(".json.xz"):
        with lzma.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

    results = data.get("results", [])

    if not isinstance(results, list):
        raise ValueError(
            "Asset index does not contain a valid 'results' list."
        )

    assets: dict[str, LocalAsset] = {}

    for item in results:
        if not isinstance(item, dict):
            continue

        if item.get("status") not in {
            "downloaded",
            "skipped",
        }:
            continue

        file_id = item.get("file_id")
        filename = item.get("filename")

        if (
            not isinstance(file_id, str)
            or not isinstance(filename, str)
        ):
            continue

        lowered = filename.lower()

        if lowered.endswith(
            (
                ".failed",
                ".part",
                ".headers",
            )
        ):
            continue

        assets[file_id] = LocalAsset(
            file_id=file_id,
            kind=str(item.get("kind") or "attachment"),
            filename=filename,
            content_type=(
                item.get("content_type")
                if isinstance(
                    item.get("content_type"),
                    str,
                )
                else None
            ),
            size_bytes=(
                item.get("size_bytes")
                if isinstance(
                    item.get("size_bytes"),
                    int,
                )
                else None
            ),
        )

    logging.info(
        "Usable local assets loaded: %d",
        len(assets),
    )

    return assets



def infer_local_content_type(path: Path) -> Optional[str]:
    suffix = path.suffix.lower()
    if suffix in LOCAL_CONTENT_TYPE_OVERRIDES:
        return LOCAL_CONTENT_TYPE_OVERRIDES[suffix]
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed


def infer_local_asset_kind(
    path: Path,
    asset_directory: Path,
    file_id: str,
) -> str:
    try:
        relative = path.resolve().relative_to(asset_directory.resolve())
        bucket = relative.parts[0].lower() if relative.parts else ""
    except ValueError:
        bucket = ""

    if bucket in {"attachment", "dictation", "image"}:
        return bucket

    content_type = infer_local_content_type(path) or ""
    if file_id.startswith("external_") and content_type.startswith("image/"):
        return "external_image"
    if content_type.startswith("image/"):
        return "image"
    return "attachment"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_local_asset_candidate(
    file_id: str,
    candidates: list[Path],
    asset_directory: Path,
) -> Optional[Path]:
    if not candidates:
        return None

    candidates = sorted(
        {path.resolve() for path in candidates},
        key=lambda path: str(path).lower(),
    )
    if len(candidates) == 1:
        return candidates[0]

    try:
        digests = {sha256_file(path) for path in candidates}
    except OSError as exc:
        logging.warning(
            "Unable to verify duplicate local assets for %s: %s",
            file_id,
            exc,
        )
        return None

    if len(digests) != 1:
        logging.warning(
            "Ambiguous local asset %s: %d different files exist; "
            "no fallback entry was selected.",
            file_id,
            len(candidates),
        )
        for path in candidates:
            logging.warning("  Candidate: %s", path)
        return None

    # The files are byte-identical. Prefer the shortest relative path and then
    # a deterministic lexical order; either copy is safe to use.
    def preference(path: Path) -> tuple[int, str]:
        try:
            relative = path.relative_to(asset_directory.resolve())
            text = relative.as_posix()
        except ValueError:
            text = str(path)
        return (len(text), text.lower())

    return min(candidates, key=preference)


def discover_local_assets(
    asset_directory: Path,
) -> dict[str, LocalAsset]:
    cache_key = os.path.normcase(os.path.abspath(str(asset_directory)))
    cached = _LOCAL_ASSET_DISCOVERY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    discovered_candidates: dict[str, list[Path]] = {}
    scanned_files = 0

    if asset_directory.is_dir():
        for path in asset_directory.rglob("*"):
            if not path.is_file():
                continue
            scanned_files += 1
            if path.suffix.lower() in LOCAL_ASSET_SKIP_SUFFIXES:
                continue
            match = LOCAL_ASSET_ID_PATTERN.match(path.name)
            if match is None:
                continue
            file_id = match.group(1)
            discovered_candidates.setdefault(file_id, []).append(path)

    discovered: dict[str, LocalAsset] = {}
    ambiguous = 0

    for file_id, candidates in discovered_candidates.items():
        selected = choose_local_asset_candidate(
            file_id,
            candidates,
            asset_directory,
        )
        if selected is None:
            ambiguous += 1
            continue

        relative = selected.resolve().relative_to(
            asset_directory.resolve()
        )
        discovered[file_id] = LocalAsset(
            file_id=file_id,
            kind=infer_local_asset_kind(
                selected,
                asset_directory,
                file_id,
            ),
            filename=relative.as_posix(),
            content_type=infer_local_content_type(selected),
            size_bytes=selected.stat().st_size,
        )

    logging.info(
        "Local asset scan: %d files, %d file IDs, %d ambiguous IDs",
        scanned_files,
        len(discovered),
        ambiguous,
    )
    _LOCAL_ASSET_DISCOVERY_CACHE[cache_key] = discovered
    return discovered


def merge_asset_sources(
    indexed_assets: dict[str, LocalAsset],
    local_assets: dict[str, LocalAsset],
    asset_directory: Path,
) -> dict[str, LocalAsset]:
    merged = dict(indexed_assets)
    added = 0
    repaired = 0

    for file_id, local_asset in local_assets.items():
        indexed = merged.get(file_id)
        if indexed is None:
            merged[file_id] = local_asset
            added += 1
            continue

        indexed_path = (
            asset_directory
            / Path(indexed.filename.replace("\\", "/"))
        ).resolve()
        if not indexed_path.is_file():
            merged[file_id] = local_asset
            repaired += 1

    logging.info(
        "Local fallback assets added: %d; broken registry paths repaired: %d",
        added,
        repaired,
    )
    logging.info("Usable local assets after merge: %d", len(merged))
    return merged


def markdown_escape_label(value: str) -> str:
    return (
        value.replace("\\\\", "\\\\\\\\")
        .replace("[", "\\\\[")
        .replace("]", "\\\\]")
        .replace("\n", " ")
        .strip()
    )


def markdown_code_span(value: str) -> str:
    """Return a Markdown code span whose rendered text is exactly *value*."""
    cleaned = value.replace("\r", " ").replace("\n", " ").strip()
    longest_backtick_run = max(
        (len(match.group(0)) for match in re.finditer(r"`+", cleaned)),
        default=0,
    )
    fence = "`" * (longest_backtick_run + 1)
    if longest_backtick_run:
        # Markdown code-span rules trim one padding space around content.
        # Padding keeps literal backticks in filenames from touching the fence.
        return f"{fence} {cleaned} {fence}"
    return f"{fence}{cleaned}{fence}"


def markdown_path(path: Path) -> str:
    return path.as_posix().replace(" ", "%20")


def asset_display_name(
    asset: LocalAsset,
) -> str:
    basename = Path(asset.filename).name

    if "__" in basename:
        basename = basename.split("__", 1)[1]

    return basename or asset.file_id


def archive_asset_path(
    asset: LocalAsset,
) -> str:
    relative = Path(
        asset.filename.replace("\\\\", "/")
    ).as_posix()

    return f"assets/{relative}"


def render_local_asset(
    *,
    file_id: str,
    part_type: str,
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
    display_name: Optional[str] = None,
    content_type_hint: Optional[str] = None,
    reference_only: bool = False,
) -> str:
    asset = assets.get(file_id)

    if asset is None:
        statistics.unresolved_assets[part_type] += 1
        return (
            f"[Unavailable asset: {file_id}]"
        )

    absolute_path = (
        asset_directory
        / Path(asset.filename.replace("\\\\", "/"))
    ).resolve()

    try:
        relative_path = absolute_path.relative_to(
            markdown_directory.resolve()
        )
    except ValueError:
        relative_path = Path(
            os.path.relpath(
                absolute_path,
                markdown_directory.resolve(),
            )
        )

    if not absolute_path.is_file():
        statistics.unresolved_assets[
            f"{part_type}:missing_local_file"
        ] += 1

        return (
            f"[Missing local asset: "
            f"{file_id}]"
        )

    target = markdown_path(relative_path)
    label = markdown_escape_label(
        display_name
        or asset_display_name(asset)
    )
    archive_path = archive_asset_path(asset)

    content_type = (
        asset.content_type
        or content_type_hint
        or ""
    ).lower()

    is_image = (
        content_type.startswith("image/")
        or asset.kind == "image"
        and Path(asset.filename).suffix.lower()
        in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
            ".bmp",
            ".svg",
        }
    )

    statistics.resolved_assets[
        "image" if is_image else asset.kind
    ] += 1

    if is_image and not reference_only:
        return (
            f"![{label}]({target})"
            "\n\n"
            f"*Asset ID: `{file_id}`  \n"
            f"Archive path: `{archive_path}`*"
        )

    if is_image:
        return (
            f"🖼 **Archived image:** [{label}]({target})  "
            "\n"
            f"Asset ID: `{file_id}`  "
            "\n"
            f"Archive path: `{archive_path}`"
        )

    if content_type.startswith("audio/") or asset.kind == "dictation":
        return (
            f"🎵 **Archived audio:** [{label}]({target})  "
            "\n"
            f"Asset ID: `{file_id}`  "
            "\n"
            f"Archive path: `{archive_path}`"
        )

    return (
        f"📎 **Archived attachment:** [{label}]({target})  "
        "\n"
        f"Asset ID: `{file_id}`  "
        "\n"
        f"Archive path: `{archive_path}`"
    )


def stringify_content_part(part: Any) -> str:
    if isinstance(part, str):
        return part

    if part is None:
        return ""

    if isinstance(part, dict):
        return json.dumps(
            part,
            ensure_ascii=False,
            indent=2,
        )

    return str(part)


def extract_text_content(
    content: dict[str, Any],
) -> str:
    parts = content.get("parts", [])

    if not isinstance(parts, list):
        return ""

    output_parts = [
        stringify_content_part(part)
        for part in parts
    ]

    return "\n".join(
        part for part in output_parts if part
    ).strip()


def describe_asset_part(
    part: dict[str, Any],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    part_type = str(
        part.get(
            "content_type",
            "unknown_asset",
        )
    )

    pointer = (
        part.get("asset_pointer")
        or part.get("pointer")
        or part.get("url")
        or part.get("file_id")
    )

    file_id = extract_file_id(pointer)

    if file_id is None:
        statistics.unresolved_assets[
            part_type
        ] += 1
        return (
            f"[Unresolved asset pointer: "
            f"{pointer or 'unknown'}]"
        )

    return render_local_asset(
        file_id=file_id,
        part_type=part_type,
        assets=assets,
        asset_directory=asset_directory,
        markdown_directory=markdown_directory,
        statistics=statistics,
    )


def extract_multimodal_content(
    content: dict[str, Any],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    parts = content.get("parts", [])

    if not isinstance(parts, list):
        return ""

    output_parts: list[str] = []

    for part in parts:
        if isinstance(part, str):
            output_parts.append(part)
            continue

        if not isinstance(part, dict):
            if part is not None:
                output_parts.append(str(part))
            continue

        part_type = part.get("content_type")

        if part_type in {
            "text",
            "input_text",
        }:
            text = part.get("text")

            if isinstance(text, str):
                output_parts.append(text)

            continue

        if part_type in {
            "image_asset_pointer",
            "audio_asset_pointer",
            "file_asset_pointer",
        }:
            output_parts.append(
                describe_asset_part(
                    part=part,
                    assets=assets,
                    asset_directory=asset_directory,
                    markdown_directory=markdown_directory,
                    statistics=statistics,
                )
            )
            continue

        output_parts.append(
            "[Unsupported multimodal part: "
            + json.dumps(
                part,
                ensure_ascii=False,
            )
            + "]"
        )

    # Multimodal parts are distinct semantic blocks.  Separate them with a
    # blank line so an image provenance paragraph can never absorb the text
    # or the next image that follows it in the same ChatGPT message.
    return "\n\n".join(
        part for part in output_parts if part
    ).strip()




def content_asset_ids(
    content: dict[str, Any],
) -> set[str]:
    identifiers: set[str] = set()
    parts = content.get("parts", [])

    if not isinstance(parts, list):
        return identifiers

    for part in parts:
        if not isinstance(part, dict):
            continue

        for key in (
            "asset_pointer",
            "pointer",
            "url",
            "file_id",
        ):
            file_id = extract_file_id(part.get(key))

            if file_id is not None:
                identifiers.add(file_id)

    return identifiers


def render_metadata_attachments(
    message: dict[str, Any],
    already_rendered_ids: set[str],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    metadata = message.get("metadata")

    if not isinstance(metadata, dict):
        return ""

    attachments = metadata.get("attachments")

    if not isinstance(attachments, list):
        return ""

    rendered: list[str] = []
    seen = set(already_rendered_ids)

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue

        file_id = extract_file_id(
            attachment.get("id")
            or attachment.get("file_id")
        )

        if file_id is None or file_id in seen:
            continue

        seen.add(file_id)

        name = attachment.get("name")
        display_name = (
            str(name)
            if isinstance(name, str) and name.strip()
            else file_id
        )

        mime_type = attachment.get("mime_type")
        content_type_hint = (
            str(mime_type)
            if isinstance(mime_type, str)
            else None
        )

        if file_id not in assets:
            statistics.unresolved_assets[
                "metadata_attachment"
            ] += 1
            rendered.append(
                "⚠ **Missing attachment:** "
                f"{markdown_code_span(display_name)}  \n"
                f"Asset ID: {markdown_code_span(file_id)}  \n"
                "Local archive status: `missing`"
            )
            continue

        rendered.append(
            render_local_asset(
                file_id=file_id,
                part_type="metadata_attachment",
                assets=assets,
                asset_directory=asset_directory,
                markdown_directory=markdown_directory,
                statistics=statistics,
                display_name=display_name,
                content_type_hint=content_type_hint,
                reference_only=True,
            )
        )

    return "\n\n".join(
        item for item in rendered if item
    )



def resolve_dictation_asset(
    file_id: str,
    assets: dict[str, LocalAsset],
    asset_directory: Path,
) -> Optional[LocalAsset]:
    """Prefer the canonical assets/dictation copy for original voice audio."""
    dictation_root = asset_directory / "dictation"
    if dictation_root.is_dir():
        candidates = sorted(
            path for path in dictation_root.glob(f"{file_id}*")
            if path.is_file() and path.stat().st_size > 0
        )
        selected = choose_local_asset_candidate(
            file_id, candidates, asset_directory
        )
        if selected is not None:
            return LocalAsset(
                file_id=file_id,
                kind="dictation",
                filename=selected.relative_to(asset_directory).as_posix(),
                content_type=infer_local_content_type(selected),
                size_bytes=selected.stat().st_size,
            )
    return assets.get(file_id)


def render_dictation_audio_reference(
    message: dict[str, Any],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    metadata = message.get("metadata")
    if not isinstance(metadata, dict):
        return ""

    pointer = metadata.get("dictation_asset_pointer")
    file_id = extract_file_id(pointer)
    if file_id is None:
        return ""

    asset = resolve_dictation_asset(file_id, assets, asset_directory)
    if asset is None:
        statistics.unresolved_assets["dictation_asset_pointer"] += 1
        return (
            "🎙 **Original dictation audio:** unavailable  \n"
            f"Asset ID: `{file_id}`  \n"
            "Archive path: `unavailable locally`"
        )

    absolute_path = (
        asset_directory / Path(asset.filename.replace("\\", "/"))
    ).resolve()
    if not absolute_path.is_file():
        statistics.unresolved_assets["dictation_asset_pointer:missing_local_file"] += 1
        return (
            "🎙 **Original dictation audio:** unavailable  \n"
            f"Asset ID: `{file_id}`  \n"
            f"Archive path: `{archive_asset_path(asset)}`"
        )

    try:
        relative_path = absolute_path.relative_to(markdown_directory.resolve())
    except ValueError:
        relative_path = Path(
            os.path.relpath(absolute_path, markdown_directory.resolve())
        )

    target = markdown_path(relative_path)
    archive_path = archive_asset_path(asset)
    statistics.resolved_assets["dictation"] += 1
    return (
        f"🎙 **Original dictation audio:** [Listen (.m4a)]({target})  \n"
        f"Asset ID: `{file_id}`  \n"
        f"Archive path: `{archive_path}`"
    )

def render_external_images_from_metadata(
    message: dict[str, Any],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    metadata = message.get("metadata")
    if not isinstance(metadata, dict):
        return ""

    references = metadata.get("_archive_external_images")
    if not isinstance(references, list):
        return ""

    rendered: list[str] = []
    seen: set[str] = set()
    for reference in references:
        if not isinstance(reference, dict):
            continue
        asset_id = reference.get("asset_id")
        if not isinstance(asset_id, str) or asset_id in seen:
            continue
        seen.add(asset_id)
        rendered.append(
            render_local_asset(
                file_id=asset_id,
                part_type="external_image",
                assets=assets,
                asset_directory=asset_directory,
                markdown_directory=markdown_directory,
                statistics=statistics,
            )
        )

    return "\n\n".join(item for item in rendered if item)


def extract_message_text(
    content: dict[str, Any],
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    content_type = content.get("content_type")

    if content_type in {
        "text",
        "code",
    }:
        return extract_text_content(content)

    if content_type == "multimodal_text":
        return extract_multimodal_content(
            content=content,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

    return ""


ENTITY_MARKER_PATTERN = re.compile(
    "\ue200entity\ue202(.*?)\ue201",
    flags=re.DOTALL,
)

INTERNAL_MARKER_PATTERN = re.compile(
    "\ue200(?P<marker_type>[A-Za-z0-9_-]+)"
    "(?:\ue202.*?)?\ue201",
    flags=re.DOTALL,
)


def replace_entity_marker(
    match: re.Match[str],
    statistics: ExportStatistics,
) -> str:
    payload = match.group(1)

    statistics.cleaned_marker_types["entity"] += 1

    try:
        decoded = json.loads(payload)

    except json.JSONDecodeError:
        logging.debug(
            "Unable to decode entity marker payload: %r",
            payload,
        )
        return ""

    if (
        isinstance(decoded, list)
        and len(decoded) >= 2
        and isinstance(decoded[1], str)
    ):
        return decoded[1]

    if isinstance(decoded, str):
        return decoded

    return ""

def replace_internal_marker(
    match: re.Match[str],
    statistics: ExportStatistics,
) -> str:
    marker_type = match.group("marker_type")

    statistics.cleaned_marker_types[
        marker_type
    ] += 1

    return ""


def replace_raw_asset_pointers(
    text: str,
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
    statistics: ExportStatistics,
) -> str:
    # Only replace raw sediment:// pointers here.
    # Bare file IDs may already be part of Markdown links generated
    # earlier by render_local_asset(); matching them again would
    # recursively wrap valid image links.
    pattern = re.compile(
        r"sediment://[^\s\])>]+"
    )

    def replace(match: re.Match[str]) -> str:
        value = match.group(0)
        file_id = extract_file_id(value)

        if file_id is None:
            return value

        return render_local_asset(
            file_id=file_id,
            part_type="raw_pointer",
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

    return pattern.sub(replace, text)


def clean_internal_markers(
    text: str,
    statistics: ExportStatistics,
) -> str:
    cleaned = ENTITY_MARKER_PATTERN.sub(
        lambda match: replace_entity_marker(
            match,
            statistics,
        ),
        text,
    )

    cleaned = INTERNAL_MARKER_PATTERN.sub(
        lambda match: replace_internal_marker(
            match,
            statistics,
        ),
        cleaned,
    )

    cleaned = re.sub(
        r"[ \t]+\n",
        "\n",
        cleaned,
    )

    cleaned = re.sub(
        r"\n{4,}",
        "\n\n\n",
        cleaned,
    )

    return cleaned.strip()


def classify_skip_reason(
    message: dict[str, Any],
) -> str:
    author = message.get("author")

    if not isinstance(author, dict):
        return "invalid_author"

    role = author.get("role")

    if is_visually_hidden(message):
        return "visually_hidden"

    if role not in VISIBLE_ROLES and not is_visible_generated_image_tool(message):
        return f"role:{role or 'unknown'}"

    content = message.get("content")

    if not isinstance(content, dict):
        return "invalid_content"

    content_type = content.get(
        "content_type",
        "unknown",
    )

    if content_type not in VISIBLE_CONTENT_TYPES:
        return f"content:{content_type}"

    return "empty"


def extract_visible_messages(
    active_path: list[dict[str, Any]],
    statistics: ExportStatistics,
    assets: dict[str, LocalAsset],
    asset_directory: Path,
    markdown_directory: Path,
) -> list[ExportMessage]:
    output: list[ExportMessage] = []

    for index, node in enumerate(active_path):
        node_id = node.get(
            "id",
            f"<node-{index}>",
        )

        message = node.get("message")

        if not isinstance(message, dict):
            statistics.skipped_reasons[
                "node_without_message"
            ] += 1
            continue

        author = message.get("author")

        if isinstance(author, dict):
            role_for_statistics = author.get(
                "role",
                "unknown",
            )
        else:
            role_for_statistics = "unknown"

        statistics.roles_in_active_path[
            str(role_for_statistics)
        ] += 1

        content = message.get("content")

        if isinstance(content, dict):
            content_type_for_statistics = (
                content.get(
                    "content_type",
                    "unknown",
                )
            )
        else:
            content_type_for_statistics = "unknown"

        statistics.content_types_in_active_path[
            str(content_type_for_statistics)
        ] += 1

        role = (
            author.get("role")
            if isinstance(author, dict)
            else None
        )

        generated_image_tool = is_visible_generated_image_tool(message)

        if (
            (role not in VISIBLE_ROLES and not generated_image_tool)
            or is_visually_hidden(message)
            or not isinstance(content, dict)
            or content.get("content_type")
            not in VISIBLE_CONTENT_TYPES
        ):
            reason = classify_skip_reason(message)
            statistics.skipped_reasons[reason] += 1
            continue

        if generated_image_tool:
            statistics.generated_image_tool_messages += 1

        raw_text = extract_message_text(
            content=content,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

        rendered_content_asset_ids = content_asset_ids(
            content
        )

        metadata_attachments = render_metadata_attachments(
            message=message,
            already_rendered_ids=rendered_content_asset_ids,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

        dictation_audio = render_dictation_audio_reference(
            message=message,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

        if not raw_text and not metadata_attachments and not dictation_audio:
            statistics.skipped_reasons[
                "empty"
            ] += 1
            continue

        external_images = render_external_images_from_metadata(
            message=message,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

        # ChatGPT places image carousels in the message text with an
        # internal ``i`` marker, for example:
        #   \ue200i\ue202turn123image0\ue202turn123image1\ue201
        # Preserve the visual position by replacing that marker before
        # the generic internal-marker cleanup removes it.
        image_marker_pattern = re.compile(
            "\ue200i(?:\ue202.*?)?\ue201",
            flags=re.DOTALL,
        )
        image_marker_replaced = False

        if external_images and image_marker_pattern.search(raw_text):
            raw_text, replacement_count = image_marker_pattern.subn(
                external_images,
                raw_text,
                count=1,
            )
            image_marker_replaced = replacement_count > 0

        cleaned_text = clean_internal_markers(
            raw_text,
            statistics,
        )

        cleaned_text = replace_raw_asset_pointers(
            text=cleaned_text,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_directory,
            statistics=statistics,
        )

        # Fallback for older or unusual exports that contain image_v2
        # metadata but no inline carousel marker.
        if external_images and not image_marker_replaced:
            cleaned_text = (
                f"{cleaned_text}\n\n{external_images}"
                if cleaned_text
                else external_images
            )

        if metadata_attachments:
            cleaned_text = (
                f"{cleaned_text}\n\n{metadata_attachments}"
                if cleaned_text
                else metadata_attachments
            )

        if dictation_audio:
            cleaned_text = (
                f"{cleaned_text}\n\n{dictation_audio}"
                if cleaned_text
                else dictation_audio
            )

        if not cleaned_text:
            statistics.skipped_reasons[
                "empty_after_cleanup"
            ] += 1
            continue

        export_role = "assistant" if generated_image_tool else str(role)

        if (
            generated_image_tool
            and output
            and output[-1].role == "assistant"
        ):
            output[-1].text = (
                f"{output[-1].text}\n\n{cleaned_text}"
                if output[-1].text
                else cleaned_text
            )
            output[-1].update_time = message.get("update_time")
            statistics.generated_image_tool_merges += 1
            continue

        output.append(
            ExportMessage(
                node_id=str(node_id),
                role=export_role,
                content_type=str(
                    content.get(
                        "content_type",
                        "unknown",
                    )
                ),
                text=cleaned_text,
                create_time=message.get(
                    "create_time"
                ),
                update_time=message.get(
                    "update_time"
                ),
            )
        )

    statistics.exported_messages = len(output)

    logging.info(
        "Visible messages extracted: %d",
        len(output),
    )

    return output


def build_conversation(
    data: dict[str, Any],
    messages: list[ExportMessage],
) -> Conversation:
    return Conversation(
        title=str(
            data.get("title")
            or "Untitled conversation"
        ),
        conversation_id=str(
            data.get("conversation_id")
            or "unknown"
        ),
        create_time=data.get("create_time"),
        update_time=data.get("update_time"),
        messages=messages,
    )


def format_timestamp(
    timestamp: Optional[float],
) -> str:
    if timestamp is None:
        return "unknown"

    try:
        date = datetime.fromtimestamp(
            timestamp
        ).astimezone()

        return date.isoformat(
            timespec="seconds"
        )

    except (
        OSError,
        OverflowError,
        TypeError,
        ValueError,
    ):
        return f"invalid timestamp: {timestamp!r}"


def escape_markdown_heading(text: str) -> str:
    return text.replace("\n", " ").strip()


def role_display_name(role: str) -> str:
    names = {
        "user": "Bruno",
        "assistant": "ChatGPT",
    }

    return names.get(
        role,
        role.capitalize(),
    )


def build_markdown_export(
    conversation: Conversation,
    include_timestamps: bool,
) -> str:
    lines: list[str] = []

    lines.append(
        f"# {escape_markdown_heading(conversation.title)}"
    )
    lines.append("")
    lines.append(
        f"- Conversation ID: "
        f"`{conversation.conversation_id}`"
    )
    lines.append(
        f"- Created: "
        f"{format_timestamp(conversation.create_time)}"
    )
    lines.append(
        f"- Updated: "
        f"{format_timestamp(conversation.update_time)}"
    )
    lines.append(
        f"- Messages: "
        f"{len(conversation.messages)}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    for message in conversation.messages:
        display_name = role_display_name(
            message.role
        )

        lines.append(f"## {display_name}")
        lines.append("")

        if include_timestamps:
            lines.append(
                f"*{format_timestamp(message.create_time)}*"
            )
            lines.append("")

        lines.append(message.text)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def build_debug_text_export(
    conversation: Conversation,
) -> str:
    lines: list[str] = []

    lines.append(conversation.title)
    lines.append("=" * len(conversation.title))
    lines.append("")
    lines.append(
        f"Conversation ID: "
        f"{conversation.conversation_id}"
    )
    lines.append(
        f"Visible messages: "
        f"{len(conversation.messages)}"
    )
    lines.append("")

    for number, message in enumerate(
        conversation.messages,
        start=1,
    ):
        lines.append("=" * 80)
        lines.append(
            f"{number:04d} | {message.role.upper()}"
        )
        lines.append(
            f"Node ID: {message.node_id}"
        )
        lines.append(
            "Create time: "
            f"{format_timestamp(message.create_time)}"
        )
        lines.append(
            f"Content type: {message.content_type}"
        )
        lines.append("-" * 80)
        lines.append(message.text)
        lines.append("")

    return "\n".join(lines)


def write_utf8_text(
    path: Path,
    content: str,
) -> None:
    logging.info(
        "Writing output file: %s",
        path,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(content)

    logging.info(
        "Output written: %d bytes",
        path.stat().st_size,
    )


def print_counter(
    counter: Counter[str],
    empty_message: str,
) -> None:
    if not counter:
        print(empty_message)
        return

    width = max(
        len(str(key))
        for key in counter
    )

    for key, count in sorted(
        counter.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        print(
            f"  {key:<{width}} : {count:5d}"
        )


def print_statistics(
    conversation: Conversation,
    statistics: ExportStatistics,
) -> None:
    print()
    print("Conversation summary")
    print("====================")
    print(
        f"Title              : "
        f"{conversation.title}"
    )
    print(
        f"Conversation ID    : "
        f"{conversation.conversation_id}"
    )
    print(
        f"All graph nodes    : "
        f"{statistics.all_nodes}"
    )
    print(
        f"Active-path nodes  : "
        f"{statistics.active_nodes}"
    )
    print(
        f"Exported messages  : "
        f"{statistics.exported_messages}"
    )
    print(
        f"Generated images   : "
        f"{statistics.generated_image_tool_messages}"
    )
    print(
        f"Merged into answer : "
        f"{statistics.generated_image_tool_merges}"
    )

    print()
    print("Skipped nodes")
    print("-------------")
    print_counter(
        statistics.skipped_reasons,
        "  None",
    )

    print()
    print("Resolved local assets")
    print("---------------------")
    print_counter(
        statistics.resolved_assets,
        "  None",
    )

    print()
    print("Unresolved assets")
    print("-----------------")
    print_counter(
        statistics.unresolved_assets,
        "  None",
    )

    print()
    print("Cleaned internal markers")
    print("------------------------")
    print_counter(
        statistics.cleaned_marker_types,
        "  None",
    )

    print()


def parse_arguments(
    script_directory: Path,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export the visible branch of a ChatGPT "
            "conversation JSON file to clean Markdown."
        )
    )

    parser.add_argument(
        "input_json",
        nargs="?",
        type=Path,
        default=(
            script_directory
            / DEFAULT_INPUT_FILENAME
        ),
        help=(
            "Input ChatGPT conversation JSON file. "
            "Default: conversation-full.json next "
            "to the script."
        ),
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=(
            "Exact Markdown output path. This overrides "
            "--output-directory."
        ),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        default=(
            ARCHIVE_ROOT
            / DEFAULT_MARKDOWN_DIRECTORY
        ),
        help=(
            "Directory used when --output is omitted. "
            "Default: markdown"
        ),
    )

    parser.add_argument(
        "--debug-output",
        action="store_true",
        help=(
            "Also create a detailed text export "
            "containing node IDs and content types."
        ),
    )

    parser.add_argument(
        "--timestamps",
        action="store_true",
        help=(
            "Include each message timestamp in "
            "the Markdown document."
        ),
    )

    parser.add_argument(
        "--asset-index",
        type=Path,
        default=(
            ARCHIVE_ROOT
            / DEFAULT_ASSET_INDEX
        ),
        help=(
            "Asset download index. Default: "
            "reports/asset-download-index-v2.json.xz"
        ),
    )

    parser.add_argument(
        "--asset-directory",
        type=Path,
        default=(
            ARCHIVE_ROOT
            / DEFAULT_ASSET_DIRECTORY
        ),
        help=(
            "Local asset root. Default: assets"
        ),
    )

    parser.add_argument(
        "--no-assets",
        action="store_true",
        help=(
            "Do not resolve local asset links."
        ),
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "Disable verbose debug logging."
        ),
    )

    return parser.parse_args()


def main() -> int:
    script_path = Path(__file__).resolve()
    script_directory = script_path.parent

    arguments = parse_arguments(
        script_directory
    )

    configure_logging(
        debug_enabled=(
            DEBUG and not arguments.quiet
        )
    )

    try:
        input_path = arguments.input_json

        if not input_path.is_absolute():
            input_path = (
                script_directory
                / input_path
            )

        input_path = input_path.resolve()

        if arguments.output is None:
            output_directory = (
                arguments.output_directory
            )

            if not output_directory.is_absolute():
                output_directory = (
                    script_directory
                    / output_directory
                )

            output_directory = (
                output_directory.resolve()
            )

            input_name = input_path.name
            if input_name.lower().endswith(".json.xz"):
                markdown_name = input_name[:-8] + ".md"
            else:
                markdown_name = input_path.with_suffix(".md").name
            markdown_path = output_directory / markdown_name
        else:
            markdown_path = arguments.output

            if not markdown_path.is_absolute():
                markdown_path = (
                    script_directory
                    / markdown_path
                )

            markdown_path = markdown_path.resolve()

        asset_index_path = arguments.asset_index

        if not asset_index_path.is_absolute():
            asset_index_path = (
                script_directory
                / asset_index_path
            )

        asset_index_path = asset_index_path.resolve()

        asset_directory = arguments.asset_directory

        if not asset_directory.is_absolute():
            asset_directory = (
                script_directory
                / asset_directory
            )

        asset_directory = asset_directory.resolve()

        logging.info(
            "Markdown directory: %s",
            markdown_path.parent,
        )
        logging.info(
            "Asset directory: %s",
            asset_directory,
        )

        statistics = ExportStatistics()

        if arguments.no_assets:
            assets: dict[str, LocalAsset] = {}
        else:
            indexed_assets = load_asset_index(
                asset_index_path
            )
            local_assets = discover_local_assets(
                asset_directory
            )
            assets = merge_asset_sources(
                indexed_assets,
                local_assets,
                asset_directory,
            )

        data = load_json(input_path)

        mapping = data["mapping"]
        current_node_id = data["current_node"]

        statistics.all_nodes = len(mapping)

        active_path = reconstruct_active_path(
            mapping=mapping,
            current_node_id=current_node_id,
        )

        statistics.active_nodes = len(
            active_path
        )

        messages = extract_visible_messages(
            active_path=active_path,
            statistics=statistics,
            assets=assets,
            asset_directory=asset_directory,
            markdown_directory=markdown_path.parent,
        )

        conversation = build_conversation(
            data=data,
            messages=messages,
        )

        markdown_content = build_markdown_export(
            conversation=conversation,
            include_timestamps=arguments.timestamps,
        )

        write_utf8_text(
            path=markdown_path,
            content=markdown_content,
        )

        if arguments.debug_output:
            debug_path = markdown_path.with_name(
                markdown_path.stem
                + "-debug.txt"
            )

            debug_content = (
                build_debug_text_export(
                    conversation
                )
            )

            write_utf8_text(
                path=debug_path,
                content=debug_content,
            )

        print_statistics(
            conversation=conversation,
            statistics=statistics,
        )

        print(
            f"Markdown export created: "
            f"{markdown_path}"
        )

        return 0

    except KeyboardInterrupt:
        logging.error(
            "Operation cancelled by user."
        )
        return 130

    except Exception as exc:
        logging.exception(
            "Export failed: %s",
            exc,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())