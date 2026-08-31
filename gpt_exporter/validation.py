"""Non-destructive validation of normalized provider outputs.

The validator never replaces canonical provider data or production outputs. It
writes disposable diagnostics below ``reports/provider-validation``. During the
migration it can also build a separate legacy SQLite oracle so production CORE
results remain checked against the historical ChatGPT indexer after the CORE
becomes authoritative.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from gpt_exporter.export.normalized import export_normalized_conversation
from gpt_exporter.index.normalized import index_normalized_file
from gpt_exporter.providers.base import ExporterProvider, ProgressCallback

with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.index import _legacy_indexer as legacy_indexer


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
    missing_message_ids: tuple[str, ...] = ()
    extra_message_ids: tuple[str, ...] = ()
    first_message_difference: str | None = None
    provenance_difference: str | None = None
    legacy_difference: str | None = None
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

    When ``compare_with_legacy_oracle`` is true, the historical indexer builds a
    disposable oracle database from the same native files. ``matched`` then
    requires both CORE shadow parity and legacy-oracle parity.
    """

    archive = Path(archive_root).expanduser().resolve()
    production_db = Path(production_database).expanduser().resolve()
    validation_root = archive / "reports" / "provider-validation" / provider.key
    markdown_root = validation_root / "markdown"
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

                if production is None or normalized is None:
                    title_matches = None
                    message_count_matches = None
                    message_content_matches = None
                    provenance_matches = None
                    origins_match = None
                    production_count = len(production[1]) if production is not None else None
                    normalized_count = len(normalized[1]) if normalized is not None else None
                    legacy_count = len(legacy[1]) if legacy is not None else None
                    legacy_matches = None
                    missing_ids: tuple[str, ...] = ()
                    extra_ids: tuple[str, ...] = ()
                    first_difference = "Conversation missing from production or shadow database."
                    provenance_difference = None
                    legacy_difference = None
                    mismatched += 1
                else:
                    (
                        production_title,
                        production_messages,
                        production_provenance,
                        production_origins,
                    ) = production
                    (
                        normalized_title,
                        normalized_messages,
                        normalized_provenance,
                        normalized_origins,
                    ) = normalized
                    production_count = len(production_messages)
                    normalized_count = len(normalized_messages)
                    title_matches = production_title == normalized_title
                    message_count_matches = production_count == normalized_count
                    message_content_matches = production_messages == normalized_messages
                    provenance_matches = production_provenance == normalized_provenance
                    origins_match = production_origins == normalized_origins
                    missing_ids, extra_ids, first_difference = _message_diagnostics(
                        production_messages,
                        normalized_messages,
                    )
                    provenance_difference = _provenance_difference(
                        production_provenance,
                        normalized_provenance,
                        production_origins,
                        normalized_origins,
                    )

                    if legacy_db is None:
                        legacy_matches = None
                        legacy_count = None
                        legacy_difference = None
                    elif legacy is None:
                        legacy_matches = False
                        legacy_count = None
                        legacy_difference = "Conversation missing from legacy oracle database."
                    else:
                        legacy_count = len(legacy[1])
                        legacy_difference = _snapshot_difference(legacy, production)
                        legacy_matches = legacy_difference is None

                    core_matches = (
                        title_matches
                        and message_count_matches
                        and message_content_matches
                        and provenance_matches
                        and origins_match
                    )
                    oracle_matches = legacy_matches is not False
                    if core_matches and oracle_matches:
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
                        production_message_count=production_count,
                        normalized_message_count=normalized_count,
                        provenance_matches=provenance_matches,
                        origins_match=origins_match,
                        legacy_matches=legacy_matches,
                        legacy_message_count=legacy_count,
                        missing_message_ids=missing_ids,
                        extra_message_ids=extra_ids,
                        first_message_difference=first_difference,
                        provenance_difference=provenance_difference,
                        legacy_difference=legacy_difference,
                    )
                )
            except Exception as error:  # Diagnostic boundary: production already succeeded.
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
                        error=str(error),
                    )
                )
    finally:
        if legacy_connection is not None:
            legacy_connection.close()

    payload = {
        "provider_key": provider.key,
        "comparison_mode": (
            "production-core+shadow-core+legacy-oracle"
            if compare_with_legacy_oracle
            else "production+shadow-core"
        ),
        "checked": len(results),
        "matched": matched,
        "mismatched": mismatched,
        "failed": failed,
        "production_database": str(production_db),
        "shadow_database": str(shadow_db),
        "legacy_oracle_database": str(legacy_db) if legacy_db is not None else None,
        "conversations": [asdict(item) for item in results],
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    _emit(
        progress,
        "Normalized shadow validation: "
        f"{matched} matched, {mismatched} mismatched, {failed} failed "
        f"({report_path})",
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


__all__ = [
    "ShadowConversationResult",
    "ShadowValidationResult",
    "run_normalized_shadow_validation",
]
