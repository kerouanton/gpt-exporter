"""Non-destructive validation of normalized provider outputs.

The validator never replaces canonical provider data or production outputs. It
writes disposable diagnostics below ``reports/provider-validation``. During the
migration it can also build separate legacy SQLite/Markdown/DOCX oracles so
production CORE results remain checked against historical ChatGPT behavior.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

from gpt_exporter.export.docx import export_docx
from gpt_exporter.export.markdown import export_markdown
from gpt_exporter.export.normalized import export_normalized_conversation
from gpt_exporter.index.normalized import index_normalized_file
from gpt_exporter.providers.base import ExporterProvider, ProgressCallback

with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.index import _legacy_indexer as legacy_indexer


ASSET_INDEX_NAME = "asset-download-index-v2.json.xz"
MessageSnapshot = tuple[str, str, str]
ProvenanceSnapshot = tuple[str, str | None, str | None, str | None, str | None, str | None, str | None]
OriginSnapshot = tuple[str, str, str, int]
DatabaseSnapshot = tuple[
    str,
    tuple[MessageSnapshot, ...],
    ProvenanceSnapshot,
    tuple[OriginSnapshot, ...],
]


@dataclass(frozen=True, slots=True)
class ShadowConversationResult:
    source: str
    conversation_id: str | None
    title_matches: bool | None
    message_count_matches: bool | None
    message_content_matches: bool | None
    production_message_count: int | None
    normalized_message_count: int | None
    provenance_matches: bool | None = None
    origins_match: bool | None = None
    legacy_matches: bool | None = None
    legacy_message_count: int | None = None
    markdown_legacy_matches: bool | None = None
    docx_legacy_matches: bool | None = None
    missing_message_ids: tuple[str, ...] = ()
    extra_message_ids: tuple[str, ...] = ()
    first_message_difference: str | None = None
    provenance_difference: str | None = None
    legacy_difference: str | None = None
    markdown_difference: str | None = None
    docx_difference: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ShadowValidationResult:
    provider_key: str
    checked: int
    matched: int
    mismatched: int
    failed: int
    report_path: Path
    shadow_database: Path
    legacy_oracle_database: Path | None
    conversations: tuple[ShadowConversationResult, ...]


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _database_snapshot(
    database_path: Path,
    conversation_id: str,
) -> DatabaseSnapshot | None:
    if not database_path.is_file():
        return None
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT title,
                   primary_origin_type,
                   primary_origin_id,
                   gizmo_id,
                   gizmo_type,
                   conversation_template_id,
                   conversation_origin,
                   default_model_slug
            FROM conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None
        messages = connection.execute(
            """
            SELECT message_id, author_role, body
            FROM messages
            WHERE conversation_id = ?
            ORDER BY message_order
            """,
            (conversation_id,),
        ).fetchall()
        origins = connection.execute(
            """
            SELECT co.origin_id, o.origin_type, co.source, co.is_primary
            FROM conversation_origins AS co
            JOIN origins AS o ON o.origin_id = co.origin_id
            WHERE co.conversation_id = ?
            ORDER BY o.origin_type, co.origin_id
            """,
            (conversation_id,),
        ).fetchall()
    finally:
        connection.close()

    provenance: ProvenanceSnapshot = (
        str(row[1] or "standard"),
        str(row[2]) if row[2] is not None else None,
        str(row[3]) if row[3] is not None else None,
        str(row[4]) if row[4] is not None else None,
        str(row[5]) if row[5] is not None else None,
        str(row[6]) if row[6] is not None else None,
        str(row[7]) if row[7] is not None else None,
    )
    return (
        str(row[0]),
        tuple(
            (str(message_id), str(role or ""), str(body or ""))
            for message_id, role, body in messages
        ),
        provenance,
        tuple(
            (
                str(origin_id),
                str(origin_type),
                str(source or ""),
                int(is_primary or 0),
            )
            for origin_id, origin_type, source, is_primary in origins
        ),
    )


def _message_diagnostics(
    production: tuple[MessageSnapshot, ...],
    normalized: tuple[MessageSnapshot, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], str | None]:
    production_ids = [message[0] for message in production]
    normalized_ids = [message[0] for message in normalized]
    production_set = set(production_ids)
    normalized_set = set(normalized_ids)
    missing = tuple(message_id for message_id in production_ids if message_id not in normalized_set)
    extra = tuple(message_id for message_id in normalized_ids if message_id not in production_set)

    first_difference: str | None = None
    for position, (expected, actual) in enumerate(zip(production, normalized), start=1):
        if expected != actual:
            first_difference = (
                f"position {position}: production={expected!r}; normalized={actual!r}"
            )
            break
    if first_difference is None and len(production) != len(normalized):
        first_difference = (
            f"message sequence length differs: production={len(production)}, "
            f"normalized={len(normalized)}"
        )

    return missing, extra, first_difference


def _provenance_difference(
    production: ProvenanceSnapshot,
    normalized: ProvenanceSnapshot,
    production_origins: tuple[OriginSnapshot, ...],
    normalized_origins: tuple[OriginSnapshot, ...],
) -> str | None:
    if production != normalized:
        names = (
            "primary_origin_type",
            "primary_origin_id",
            "gizmo_id",
            "gizmo_type",
            "conversation_template_id",
            "conversation_origin",
            "default_model_slug",
        )
        for name, expected, actual in zip(names, production, normalized):
            if expected != actual:
                return f"{name}: production={expected!r}; normalized={actual!r}"
    if production_origins != normalized_origins:
        return (
            "conversation_origins differ: "
            f"production={production_origins!r}; normalized={normalized_origins!r}"
        )
    return None


def _snapshot_difference(expected: DatabaseSnapshot, actual: DatabaseSnapshot) -> str | None:
    if expected[0] != actual[0]:
        return f"title: legacy={expected[0]!r}; production={actual[0]!r}"
    if expected[1] != actual[1]:
        _missing, _extra, difference = _message_diagnostics(expected[1], actual[1])
        return difference or "messages differ"
    difference = _provenance_difference(expected[2], actual[2], expected[3], actual[3])
    if difference is not None:
        return difference
    return None


def _text_difference(expected: str, actual: str) -> str | None:
    if expected == actual:
        return None
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    for line_number, (left, right) in enumerate(zip(expected_lines, actual_lines), start=1):
        if left != right:
            return (
                f"line {line_number}: legacy_sha256={hashlib.sha256(left.encode()).hexdigest()[:16]}; "
                f"core_sha256={hashlib.sha256(right.encode()).hexdigest()[:16]}"
            )
    return f"line count differs: legacy={len(expected_lines)}; core={len(actual_lines)}"


def _resolved_relationship_target(docx_path: Path, target: str, target_mode: str) -> str:
    """Return a stable semantic target for one OOXML relationship."""

    if target_mode.casefold() != "external":
        return target

    parsed = urlparse(target)
    if parsed.scheme.casefold() in {"http", "https", "mailto"}:
        return target

    if parsed.scheme.casefold() == "file":
        raw_path = unquote(parsed.path)
        if os.name == "nt" and raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return str(Path(raw_path).resolve())

    portable = unquote(target).replace("\\", os.sep).replace("/", os.sep)
    return str((docx_path.parent / portable).resolve())


def _relationship_fingerprint(path: Path, xml_bytes: bytes) -> str:
    root = ElementTree.fromstring(xml_bytes)
    relationships: list[tuple[str, str, str, str]] = []
    for relationship in root:
        relationship_id = relationship.attrib.get("Id", "")
        relationship_type = relationship.attrib.get("Type", "")
        target_mode = relationship.attrib.get("TargetMode", "")
        target = relationship.attrib.get("Target", "")
        relationships.append(
            (
                relationship_id,
                relationship_type,
                target_mode,
                _resolved_relationship_target(path, target, target_mode),
            )
        )
    relationships.sort()
    return hashlib.sha256(repr(relationships).encode("utf-8")).hexdigest()


def _docx_fingerprint(path: Path) -> tuple[tuple[str, str], ...]:
    """Fingerprint semantic DOCX members while ignoring volatile metadata."""

    ignored = {"docProps/core.xml"}
    semantic_relationships = {"word/_rels/document.xml.rels"}
    with zipfile.ZipFile(path, "r") as archive:
        members = []
        for name in sorted(archive.namelist()):
            if name in ignored or name.endswith("/"):
                continue
            content = archive.read(name)
            if name in semantic_relationships:
                digest = _relationship_fingerprint(path, content)
            else:
                digest = hashlib.sha256(content).hexdigest()
            members.append((name, digest))
    return tuple(members)


def _compare_export_oracle(
    provider: ExporterProvider,
    source: Path,
    *,
    archive: Path,
    oracle_root: Path,
    conversation_id: str,
) -> tuple[bool, str | None, bool | None, str | None]:
    """Compare freshly generated CORE and legacy exports from the same source.

    Full-archive validation must not compare a freshly generated legacy DOCX to
    an arbitrary historical production DOCX: older production files may have
    been created by previous converter versions. Both DOCX sides are therefore
    generated into the disposable validation tree from their respective fresh
    Markdown outputs.
    """

    oracle_root.mkdir(parents=True, exist_ok=True)
    core_markdown = oracle_root / f"{conversation_id}-core.md"
    legacy_markdown = oracle_root / f"{conversation_id}-legacy.md"

    conversation = provider.normalize_conversation(
        source,
        asset_directory=archive / "assets",
        markdown_directory=oracle_root,
        asset_index_path=archive / "reports" / ASSET_INDEX_NAME,
    )
    export_normalized_conversation(conversation, core_markdown, overwrite=True)
    export_markdown(
        source,
        legacy_markdown,
        asset_index_path=archive / "reports" / ASSET_INDEX_NAME,
        asset_directory=archive / "assets",
    )
    core_text = core_markdown.read_text(encoding="utf-8")
    legacy_text = legacy_markdown.read_text(encoding="utf-8")
    markdown_difference = _text_difference(legacy_text, core_text)
    markdown_matches = markdown_difference is None

    core_docx = oracle_root / f"{conversation_id}-core.docx"
    legacy_docx = oracle_root / f"{conversation_id}-legacy.docx"
    export_docx(core_markdown, core_docx, overwrite=True)
    export_docx(legacy_markdown, legacy_docx, overwrite=True)
    core_fingerprint = _docx_fingerprint(core_docx)
    legacy_fingerprint = _docx_fingerprint(legacy_docx)
    docx_matches = legacy_fingerprint == core_fingerprint
    docx_difference = None
    if not docx_matches:
        legacy_members = dict(legacy_fingerprint)
        core_members = dict(core_fingerprint)
        names = sorted(set(legacy_members) | set(core_members))
        for name in names:
            if legacy_members.get(name) != core_members.get(name):
                docx_difference = f"DOCX member differs: {name}"
                break
        if docx_difference is None:
            docx_difference = "DOCX semantic fingerprints differ"
    return markdown_matches, markdown_difference, docx_matches, docx_difference


def run_normalized_shadow_validation(
    provider: ExporterProvider,
    source_files: Iterable[Path | str],
    *,
    archive_root: Path | str,
    production_database: Path | str,
    compare_with_legacy_oracle: bool = False,
    progress: ProgressCallback | None = None,
) -> ShadowValidationResult:
    """Exercise CORE outputs without changing production outputs.

    When ``compare_with_legacy_oracle`` is true, historical index/export paths
    build disposable oracles from the same native files. ``matched`` then
    requires CORE shadow parity plus legacy index and export parity.
    """

    archive = Path(archive_root).expanduser().resolve()
    production_db = Path(production_database).expanduser().resolve()
    validation_root = archive / "reports" / "provider-validation" / provider.key
    markdown_root = validation_root / "markdown"
    export_oracle_root = validation_root / "export-oracle"
    shadow_db = validation_root / "conversations-index-shadow.sqlite"
    legacy_db = (
        validation_root / "conversations-index-legacy-oracle.sqlite"
        if compare_with_legacy_oracle
        else None
    )
    report_path = validation_root / "latest.json"

    if validation_root.exists():
        shutil.rmtree(validation_root)
    markdown_root.mkdir(parents=True, exist_ok=True)

    legacy_connection = None
    if legacy_db is not None:
        legacy_connection = legacy_indexer.connect_database(legacy_db)

    results: list[ShadowConversationResult] = []
    matched = 0
    mismatched = 0
    failed = 0

    try:
        for raw_source in source_files:
            source = Path(raw_source).expanduser().resolve()
            try:
                conversation = provider.normalize_conversation(source)
                export_normalized_conversation(
                    conversation,
                    markdown_root / f"{conversation.conversation_id}.md",
                    overwrite=True,
                )
                index_normalized_file(
                    provider,
                    source,
                    archive_root=archive,
                    database_path=shadow_db,
                )
                if legacy_connection is not None:
                    legacy_indexer.index_one(
                        legacy_connection,
                        source,
                        archive,
                        force=True,
                    )

                production = _database_snapshot(production_db, conversation.conversation_id)
                normalized = _database_snapshot(shadow_db, conversation.conversation_id)
                legacy = (
                    _database_snapshot(legacy_db, conversation.conversation_id)
                    if legacy_db is not None
                    else None
                )

                if compare_with_legacy_oracle:
                    (
                        markdown_legacy_matches,
                        markdown_difference,
                        docx_legacy_matches,
                        docx_difference,
                    ) = _compare_export_oracle(
                        provider,
                        source,
                        archive=archive,
                        oracle_root=export_oracle_root,
                        conversation_id=conversation.conversation_id,
                    )
                else:
                    markdown_legacy_matches = None
                    markdown_difference = None
                    docx_legacy_matches = None
                    docx_difference = None

                if production is None or normalized is None:
                    result = ShadowConversationResult(
                        source=str(source),
                        conversation_id=conversation.conversation_id,
                        title_matches=False,
                        message_count_matches=False,
                        message_content_matches=False,
                        production_message_count=(len(production[1]) if production else None),
                        normalized_message_count=(len(normalized[1]) if normalized else None),
                        error="conversation missing from production or shadow database",
                    )
                    mismatched += 1
                    results.append(result)
                    continue

                missing, extra, first_difference = _message_diagnostics(
                    production[1], normalized[1]
                )
                provenance_difference = _provenance_difference(
                    production[2], normalized[2], production[3], normalized[3]
                )
                legacy_difference = (
                    _snapshot_difference(legacy, production)
                    if legacy is not None
                    else None
                )
                title_matches = production[0] == normalized[0]
                message_count_matches = len(production[1]) == len(normalized[1])
                message_content_matches = production[1] == normalized[1]
                provenance_matches = production[2] == normalized[2]
                origins_match = production[3] == normalized[3]
                legacy_matches = legacy_difference is None if legacy is not None else None
                conversation_matches = (
                    title_matches
                    and message_count_matches
                    and message_content_matches
                    and provenance_matches
                    and origins_match
                    and (legacy_matches is not False)
                    and (markdown_legacy_matches is not False)
                    and (docx_legacy_matches is not False)
                )

                if conversation_matches:
                    matched += 1
                else:
                    mismatched += 1

                results.append(
                    ShadowConversationResult(
                        source=str(source),
                        conversation_id=conversation.conversation_id,
                        title_matches=title_matches,
                        message_count_matches=message_count_matches,
                        message_content_matches=message_content_matches,
                        production_message_count=len(production[1]),
                        normalized_message_count=len(normalized[1]),
                        provenance_matches=provenance_matches,
                        origins_match=origins_match,
                        legacy_matches=legacy_matches,
                        legacy_message_count=(len(legacy[1]) if legacy is not None else None),
                        markdown_legacy_matches=markdown_legacy_matches,
                        docx_legacy_matches=docx_legacy_matches,
                        missing_message_ids=missing,
                        extra_message_ids=extra,
                        first_message_difference=first_difference,
                        provenance_difference=provenance_difference,
                        legacy_difference=legacy_difference,
                        markdown_difference=markdown_difference,
                        docx_difference=docx_difference,
                    )
                )
            except Exception as error:  # validation must report individual failures
                failed += 1
                results.append(
                    ShadowConversationResult(
                        source=str(source),
                        conversation_id=None,
                        title_matches=None,
                        message_count_matches=None,
                        message_content_matches=None,
                        production_message_count=None,
                        normalized_message_count=None,
                        error=f"{type(error).__name__}: {error}",
                    )
                )
    finally:
        if legacy_connection is not None:
            legacy_connection.close()

    validation_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider_key": provider.key,
        "checked": len(results),
        "matched": matched,
        "mismatched": mismatched,
        "failed": failed,
        "shadow_database": str(shadow_db),
        "legacy_oracle_database": str(legacy_db) if legacy_db is not None else None,
        "conversations": [asdict(item) for item in results],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(
        progress,
        f"Normalized shadow validation: {matched} matched, {mismatched} mismatched, "
        f"{failed} failed ({report_path})",
    )
    return ShadowValidationResult(
        provider_key=provider.key,
        checked=len(results),
        matched=matched,
        mismatched=mismatched,
        failed=failed,
        report_path=report_path,
        shadow_database=shadow_db,
        legacy_oracle_database=legacy_db,
        conversations=tuple(results),
    )
