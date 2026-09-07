"""Verify the real legacy cutover using only canonical archive downloads."""

from __future__ import annotations

import argparse
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path

from gpt_exporter.index import rebuild_index
from gpt_exporter.paths import default_archive_paths


EXPECTED_CONVERSATIONS = 42
EXPECTED_MESSAGES = 654
EXPECTED_ROLES = {"user": 304, "assistant": 311, "unknown": 39}


def verify_cutover(
    archive_root: Path,
    *,
    expected_conversations: int = EXPECTED_CONVERSATIONS,
    expected_messages: int = EXPECTED_MESSAGES,
    expected_roles: dict[str, int] | None = None,
) -> dict[str, object]:
    archive_root = Path(archive_root).expanduser().resolve()
    downloads = archive_root / "downloads"
    if not downloads.is_dir():
        raise FileNotFoundError(downloads)
    role_expectation = EXPECTED_ROLES if expected_roles is None else expected_roles

    with tempfile.TemporaryDirectory(prefix="gpt-exporter-legacy-cutover-") as temporary:
        database = Path(temporary) / "cutover-check.sqlite"
        result = rebuild_index(
            archive_root,
            downloads_dir=downloads,
            database_path=database,
        )
        if not result.success:
            failures = "; ".join(
                f"{item.source_path.name}: {item.error_type}: {item.message}"
                for item in result.failures
            )
            raise RuntimeError(f"Temporary archive rebuild failed: {failures}")

        with closing(sqlite3.connect(database)) as connection:
            conversation_count = connection.execute(
                "SELECT COUNT(*) FROM conversations WHERE conversation_id LIKE 'legacy-docx-%'"
            ).fetchone()[0]
            message_count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id LIKE 'legacy-docx-%'"
            ).fetchone()[0]
            role_rows = connection.execute(
                """
                SELECT author_role, COUNT(*)
                FROM messages
                WHERE conversation_id LIKE 'legacy-docx-%'
                GROUP BY author_role
                """
            ).fetchall()
            roles = Counter({str(role): int(count) for role, count in role_rows})
            canonical_source_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM canonical_conversation_sources
                WHERE conversation_id LIKE 'legacy-docx-%' AND provider_id = 'gpt'
                """
            ).fetchone()[0]
            docx_dependency_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM conversations
                WHERE conversation_id LIKE 'legacy-docx-%' AND docx_path IS NOT NULL
                """
            ).fetchone()[0]

    expected_roles_counter = Counter(role_expectation)
    success = (
        conversation_count == expected_conversations
        and message_count == expected_messages
        and roles == expected_roles_counter
        and canonical_source_count == expected_conversations
        and docx_dependency_count == 0
    )
    return {
        "success": success,
        "conversations": conversation_count,
        "messages": message_count,
        "roles": dict(sorted(roles.items())),
        "canonical_sources": canonical_source_count,
        "docx_dependencies": docx_dependency_count,
        "expected_conversations": expected_conversations,
        "expected_messages": expected_messages,
        "expected_roles": dict(sorted(expected_roles_counter.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild a temporary archive index using only downloads JSON/XZ and verify "
            "that the promoted 42 legacy conversations no longer depend on DOCX."
        )
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=default_archive_paths().root,
    )
    args = parser.parse_args(argv)

    result = verify_cutover(args.archive_root)
    print(f"Legacy conversations: {result['conversations']} / {result['expected_conversations']}")
    print(f"Legacy messages: {result['messages']} / {result['expected_messages']}")
    print(f"Legacy roles: {result['roles']}")
    print(f"Expected roles: {result['expected_roles']}")
    print(f"Canonical GPT sources: {result['canonical_sources']}")
    print(f"DOCX dependencies in rebuilt index: {result['docx_dependencies']}")
    print(f"Cutover status: {'PASS' if result['success'] else 'FAIL'}")
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
