"""Extract embedded media from immutable legacy DOCX sources.

The historical DOCX remains authoritative. This module copies relationship
payloads into a derived asset tree and records the Word body-block order where
each relationship was referenced. It never rewrites the source document.
"""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from docx import Document
from docx.oxml.ns import qn


LEGACY_ASSET_EXPORT_VERSION = "legacy-asset-export-v1"
_IMAGE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
_OLE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
_PACKAGE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/package"
_SUPPORTED_REL_TYPES = {_IMAGE_REL, _OLE_REL, _PACKAGE_REL}


@dataclass(frozen=True, slots=True)
class LegacyAsset:
    """One copied asset plus its relationship/provenance information."""

    block_order: int
    relationship_id: str
    kind: str
    content_type: str
    source_part_name: str
    sha256: str
    output_path: Path


@dataclass(frozen=True, slots=True)
class LegacyAssetExport:
    """Result of copying all supported body assets from one legacy DOCX."""

    assets: tuple[LegacyAsset, ...]
    unresolved_relationships: tuple[tuple[int, str], ...]

    @property
    def image_count(self) -> int:
        return sum(asset.kind == "image" for asset in self.assets)

    @property
    def attachment_count(self) -> int:
        return sum(asset.kind == "attachment" for asset in self.assets)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_filename(value: str) -> str:
    value = value.strip().replace("\\", "_").replace("/", "_")
    value = re.sub(r"[<>:\"|?*\x00-\x1f]", "_", value)
    return value or "asset.bin"


def _candidate_relationship_ids(rels) -> set[str]:
    """Return only relationship IDs that could contain supported legacy assets."""
    candidates: set[str] = set()
    for relationship_id, relationship in rels.items():
        reltype = str(getattr(relationship, "reltype", ""))
        target_part = getattr(relationship, "target_part", None)
        content_type = str(getattr(target_part, "content_type", "")) if target_part is not None else ""
        if reltype in _SUPPORTED_REL_TYPES or content_type.lower().startswith("image/"):
            candidates.add(str(relationship_id))
    return candidates


def _relationship_ids(element, candidates: set[str]) -> tuple[str, ...]:
    """Return supported asset relationship IDs referenced by one body block.

    This deliberately avoids three XPath queries per Word body block. Once the
    document relationship table tells us which rIds can possibly be assets, a
    single lightweight descendant traversal is enough to locate their body
    occurrences and preserve block order.
    """
    if not candidates:
        return ()

    ids: list[str] = []
    for node in element.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "blip":
            relationship_id = node.get(qn("r:embed"))
        elif local in {"imagedata", "OLEObject"}:
            relationship_id = node.get(qn("r:id"))
        else:
            continue
        if relationship_id and relationship_id in candidates:
            ids.append(relationship_id)

    return tuple(dict.fromkeys(ids))


def _target_blob(relationship) -> tuple[bytes, str, str] | None:
    if getattr(relationship, "is_external", False):
        return None
    target_part = getattr(relationship, "target_part", None)
    if target_part is None:
        return None
    blob = getattr(target_part, "blob", None)
    if not isinstance(blob, bytes):
        return None
    part_name = str(getattr(target_part, "partname", "asset.bin"))
    content_type = str(getattr(target_part, "content_type", "application/octet-stream"))
    return blob, part_name, content_type


def _kind(relationship, content_type: str) -> str | None:
    reltype = str(getattr(relationship, "reltype", ""))
    if reltype == _IMAGE_REL or content_type.lower().startswith("image/"):
        return "image"
    if reltype in {_OLE_REL, _PACKAGE_REL}:
        return "attachment"
    return None


def _output_name(part_name: str, content_type: str, digest: str) -> str:
    original = PurePosixPath(part_name).name or "asset"
    original = _safe_filename(original)
    suffix = Path(original).suffix
    if not suffix:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
        original += guessed
    return f"{digest[:16]}__{original}"


def extract_legacy_assets(
    source_docx: Path,
    asset_root: Path,
    *,
    source_sha256: str,
) -> LegacyAssetExport:
    """Copy body images and embedded packages from ``source_docx``.

    Assets are content-addressed inside a source-specific directory so Word's
    repetitive internal names (for example ``image1.png``) cannot collide
    across historical conversations.
    """

    source_docx = Path(source_docx).expanduser().resolve()
    asset_root = Path(asset_root).expanduser().resolve()
    document = Document(source_docx)
    rels = document.part.rels
    candidate_ids = _candidate_relationship_ids(rels)

    # Most historical conversations contain no embedded media. Avoid walking
    # tens of thousands of Word body blocks when the relationship table proves
    # there is nothing to export.
    if not candidate_ids:
        return LegacyAssetExport(assets=(), unresolved_relationships=())

    conversation_root = asset_root / source_sha256[:16]
    exported: list[LegacyAsset] = []
    unresolved: list[tuple[int, str]] = []
    written: dict[str, Path] = {}

    for order, item in enumerate(document.iter_inner_content()):
        element = getattr(item, "_element", None)
        if element is None:
            continue
        for relationship_id in _relationship_ids(element, candidate_ids):
            relationship = rels.get(relationship_id)
            if relationship is None:
                unresolved.append((order, relationship_id))
                continue

            payload = _target_blob(relationship)
            if payload is None:
                unresolved.append((order, relationship_id))
                continue
            blob, part_name, content_type = payload
            kind = _kind(relationship, content_type)
            if kind is None:
                continue

            digest = _sha256_bytes(blob)
            output_path = written.get(digest)
            if output_path is None:
                conversation_root.mkdir(parents=True, exist_ok=True)
                output_path = conversation_root / _output_name(part_name, content_type, digest)
                if output_path.is_file():
                    if _sha256_bytes(output_path.read_bytes()) != digest:
                        raise ValueError(f"Legacy asset path collision: {output_path}")
                else:
                    output_path.write_bytes(blob)
                written[digest] = output_path

            exported.append(
                LegacyAsset(
                    block_order=order,
                    relationship_id=relationship_id,
                    kind=kind,
                    content_type=content_type,
                    source_part_name=part_name,
                    sha256=digest,
                    output_path=output_path,
                )
            )

    return LegacyAssetExport(
        assets=tuple(exported),
        unresolved_relationships=tuple(unresolved),
    )
