"""Compatibility shell around the retained ChatGPT index CLI."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from gpt_exporter.index.storage import connect_database
from . import rebuild_index as rebuild_provider_index
from . import update_index as update_provider_index


with contextlib.redirect_stdout(io.StringIO()):
    from . import _native_indexer as implementation


def _build_index_v5(
    downloads_dir: Path,
    archive_root: Path,
    database_path: Path,
    *,
    force: bool = False,
) -> None:
    result = update_provider_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        force=force,
        progress=print,
    )
    if result.failed:
        raise RuntimeError(f"Index completed with {result.failed} source failure(s)")


def _rebuild_index_v5(
    downloads_dir: Path,
    archive_root: Path,
    database_path: Path,
) -> None:
    result = rebuild_provider_index(
        archive_root,
        downloads_dir=downloads_dir,
        database_path=database_path,
        progress=print,
    )
    if result.failed:
        raise RuntimeError(f"Rebuild completed with {result.failed} source failure(s)")


def _show_conversation_v5(database_path: Path, selector: str) -> None:
    with connect_database(database_path) as connection:
        conversation = implementation.resolve_conversation(connection, selector)
        conversation_id = conversation["conversation_id"]
        row = connection.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        metadata_row = connection.execute(
            """
            SELECT metadata_json
            FROM conversation_provider_metadata
            WHERE conversation_id = ? AND provider_id = 'gpt'
            """,
            (conversation_id,),
        ).fetchone()
        metadata = json.loads(metadata_row["metadata_json"]) if metadata_row else {}
        project_rows = connection.execute(
            """
            SELECT wp.name FROM conversation_work_projects AS cwp
            JOIN work_projects AS wp ON wp.project_id = cwp.project_id
            WHERE cwp.conversation_id = ? ORDER BY wp.name COLLATE NOCASE
            """,
            (conversation_id,),
        ).fetchall()
        category_rows = connection.execute(
            """
            SELECT cat.name FROM conversation_categories AS cc
            JOIN categories AS cat ON cat.category_id = cc.category_id
            WHERE cc.conversation_id = ? ORDER BY cat.name COLLATE NOCASE
            """,
            (conversation_id,),
        ).fetchall()
        tag_rows = connection.execute(
            """
            SELECT t.name FROM conversation_tags AS ct
            JOIN tags AS t ON t.tag_id = ct.tag_id
            WHERE ct.conversation_id = ? ORDER BY t.name COLLATE NOCASE
            """,
            (conversation_id,),
        ).fetchall()
        origin_rows = connection.execute(
            """
            SELECT o.origin_type, o.origin_id, o.label, co.source, co.is_primary
            FROM conversation_origins AS co
            JOIN origins AS o ON o.origin_id = co.origin_id
            WHERE co.conversation_id = ?
            ORDER BY co.is_primary DESC, o.origin_type, o.origin_id
            """,
            (conversation_id,),
        ).fetchall()

    print(f"Title: {row['title']}")
    print(f"ID: {row['conversation_id']}")
    print(f"Created: {row['created_at'] or 'unknown'}")
    print(f"Updated: {row['updated_at'] or 'unknown'}")
    print(f"Model: {metadata.get('default_model_slug') or 'unknown'}")
    print(f"DOCX: {row['docx_path'] or 'not found'}")
    print(f"JSON: {row['source_json_path']}")
    print(f"Top-level gizmo_id: {metadata.get('gizmo_id') or '—'}")
    print(f"Top-level gizmo_type: {metadata.get('gizmo_type') or '—'}")
    print(f"Conversation template: {metadata.get('conversation_template_id') or '—'}")
    print(f"Conversation origin: {metadata.get('conversation_origin') or '—'}")
    print("Projects: " + (", ".join(item["name"] for item in project_rows) if project_rows else "—"))
    print("Categories: " + (", ".join(item["name"] for item in category_rows) if category_rows else "—"))
    print("Tags: " + (", ".join(item["name"] for item in tag_rows) if tag_rows else "—"))
    if origin_rows:
        print("Origins:")
        for origin in origin_rows:
            primary = " [primary]" if origin["is_primary"] else ""
            label = f" — {origin['label']}" if origin["label"] else ""
            print(f"  {origin['origin_type']}: {origin['origin_id']}{label}{primary}")
            print(f"    source: {origin['source']}")
    else:
        print("Origins: standard ChatGPT")


def _patch_implementation() -> None:
    implementation.SCHEMA_VERSION = 5
    implementation.connect_database = connect_database
    implementation.build_index = _build_index_v5
    implementation.rebuild_index = _rebuild_index_v5
    implementation.show_conversation = _show_conversation_v5


_patch_implementation()


def main() -> int:
    return implementation.main()


__all__ = ["implementation", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
