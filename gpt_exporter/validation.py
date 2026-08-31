"""Non-destructive validation of normalized provider outputs against production.

The shadow validator never replaces canonical provider data or production
outputs. It writes disposable diagnostics below ``reports/provider-validation``
and uses a separate SQLite database so the provider-neutral export/index path can
be exercised on real archive updates before it becomes authoritative.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from gpt_exporter.export.normalized import export_normalized_conversation
from gpt_exporter.index.normalized import index_normalized_file
from gpt_exporter.providers.base import ExporterProvider, ProgressCallback


@dataclass(frozen=True, slots=True)
class ShadowConversationResult:
    source: str
    conversation_id: str | None
    title_matches: bool | None
    message_count_matches: bool | None
    production_message_count: int | None
    normalized_message_count: int | None
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
    conversations: tuple[ShadowConversationResult, ...]


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _production_snapshot(
    database_path: Path,
    conversation_id: str,
) -> tuple[str, int] | None:
    if not database_path.is_file():
        return None
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT c.title, COUNT(m.message_id)
            FROM conversations AS c
            LEFT JOIN messages AS m ON m.conversation_id = c.conversation_id
            WHERE c.conversation_id = ?
            GROUP BY c.conversation_id, c.title
            """,
            (conversation_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return str(row[0]), int(row[1])


def run_normalized_shadow_validation(
    provider: ExporterProvider,
    source_files: Iterable[Path | str],
    *,
    archive_root: Path | str,
    production_database: Path | str,
    progress: ProgressCallback | None = None,
) -> ShadowValidationResult:
    """Exercise normalized Markdown/index paths without changing production outputs."""

    archive = Path(archive_root).expanduser().resolve()
    production_db = Path(production_database).expanduser().resolve()
    validation_root = archive / "reports" / "provider-validation" / provider.key
    markdown_root = validation_root / "markdown"
    shadow_db = validation_root / "conversations-index-shadow.sqlite"
    report_path = validation_root / "latest.json"

    if validation_root.exists():
        shutil.rmtree(validation_root)
    markdown_root.mkdir(parents=True, exist_ok=True)

    results: list[ShadowConversationResult] = []
    matched = 0
    mismatched = 0
    failed = 0

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

            production = _production_snapshot(production_db, conversation.conversation_id)
            if production is None:
                title_matches = None
                message_count_matches = None
                production_count = None
                mismatched += 1
            else:
                production_title, production_count = production
                title_matches = production_title == (conversation.title or "Untitled conversation")
                message_count_matches = production_count == conversation.message_count
                if title_matches and message_count_matches:
                    matched += 1
                else:
                    mismatched += 1

            results.append(
                ShadowConversationResult(
                    source=str(source),
                    conversation_id=conversation.conversation_id,
                    title_matches=title_matches,
                    message_count_matches=message_count_matches,
                    production_message_count=production_count,
                    normalized_message_count=conversation.message_count,
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
                    production_message_count=None,
                    normalized_message_count=None,
                    error=str(error),
                )
            )

    payload = {
        "provider_key": provider.key,
        "checked": len(results),
        "matched": matched,
        "mismatched": mismatched,
        "failed": failed,
        "production_database": str(production_db),
        "shadow_database": str(shadow_db),
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
        conversations=tuple(results),
    )


__all__ = [
    "ShadowConversationResult",
    "ShadowValidationResult",
    "run_normalized_shadow_validation",
]
