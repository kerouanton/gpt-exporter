"""Provider-neutral conversation browser package.

The historical browser module uses a bare ``import archive_core``. Install a
package-local compatibility alias before that module is imported so the shared
browser remains self-contained and continues to work when provider packages or
repository-root compatibility scripts are absent.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from . import archive_core as _archive_core


_original_matching_message_excerpts = _archive_core.matching_message_excerpts


def _matching_message_excerpts_with_author_names(
    database_path: Path,
    conversation_id: str,
    query: str,
    *,
    limit: int = 8,
    excerpt_chars: int = 700,
) -> list[dict[str, Any]]:
    """Prefer canonical author names while keeping role fallback compatibility."""
    excerpts = _original_matching_message_excerpts(
        database_path,
        conversation_id,
        query,
        limit=limit,
        excerpt_chars=excerpt_chars,
    )
    if not excerpts:
        return excerpts

    orders = sorted({int(item["message_order"]) for item in excerpts})
    placeholders = ",".join("?" for _ in orders)
    with _archive_core.connect_database(Path(database_path), readonly=True) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(messages)").fetchall()
        }
        if "author_name" not in columns:
            return excerpts
        rows = connection.execute(
            f"""
            SELECT message_order, author_name
            FROM messages
            WHERE conversation_id = ?
              AND message_order IN ({placeholders})
            """,
            (conversation_id, *orders),
        ).fetchall()

    names = {
        int(row["message_order"]): str(row["author_name"]).strip()
        for row in rows
        if row["author_name"] is not None and str(row["author_name"]).strip()
    }
    for item in excerpts:
        author_name = names.get(int(item["message_order"]))
        if author_name:
            item["author_role"] = author_name
    return excerpts


_archive_core.matching_message_excerpts = _matching_message_excerpts_with_author_names
sys.modules.setdefault("archive_core", _archive_core)

__all__: list[str] = []
