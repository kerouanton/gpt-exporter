"""Provider-neutral SQLite storage helpers for the conversation archive."""

from __future__ import annotations

import datetime as dt
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 4
LOGGER = logging.getLogger("gpt_exporter.index")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: Any) -> str:
    """Return a stable human-readable string without provider assumptions."""
    if value is None:
        return ""
    if isinstance(value, str):
        return WHITESPACE_RE.sub(" ", value).strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (normalize_text(item) for item in value))).strip()
    if isinstance(value, dict):
        if "text" in value:
            return normalize_text(value["text"])
        if "parts" in value:
            return normalize_text(value["parts"])
    return ""


def now_iso() -> str:
    """Return the current local timestamp in ISO 8601 format."""
    return dt.datetime.now().astimezone().isoformat()


def schema_exists(connection: sqlite3.Connection) -> bool:
    """Return True if an existing conversations table is present."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'"
    ).fetchone()
    return row is not None


def create_schema(connection: sqlite3.Connection) -> None:
    """Create the current archive schema.

    Provider-specific compatibility columns remain nullable for schema stability;
    new provider-neutral data is carried by canonical conversation metadata.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            conversation_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            source_json_path TEXT NOT NULL,
            source_mtime_ns INTEGER NOT NULL,
            docx_path TEXT,
            indexed_at TEXT NOT NULL,

            primary_origin_type TEXT NOT NULL DEFAULT 'standard',
            primary_origin_id TEXT,
            gizmo_id TEXT,
            gizmo_type TEXT,
            conversation_template_id TEXT,
            conversation_origin TEXT,
            default_model_slug TEXT
        );

        CREATE INDEX IF NOT EXISTS conversations_title_idx
            ON conversations(title COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS conversations_created_at_idx
            ON conversations(created_at);
        CREATE INDEX IF NOT EXISTS conversations_primary_origin_idx
            ON conversations(primary_origin_type, primary_origin_id);

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            message_id TEXT NOT NULL,
            message_order INTEGER NOT NULL,
            author_role TEXT NOT NULL,
            created_at TEXT,
            content_type TEXT,
            body TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
            ON messages(conversation_id);

        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            body,
            title,
            conversation_id UNINDEXED,
            message_id UNINDEXED,
            author_role UNINDEXED
        );

        CREATE TABLE IF NOT EXISTS origins (
            origin_id TEXT PRIMARY KEY,
            origin_type TEXT NOT NULL,
            label TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS origins_type_idx
            ON origins(origin_type);

        CREATE TABLE IF NOT EXISTS conversation_origins (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            origin_id TEXT NOT NULL REFERENCES origins(origin_id)
                ON DELETE CASCADE,
            source TEXT NOT NULL,
            is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0, 1)),
            PRIMARY KEY (conversation_id, origin_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_origins_origin_idx
            ON conversation_origins(origin_id);

        CREATE TABLE IF NOT EXISTS categories (
            category_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_categories (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            category_id INTEGER NOT NULL REFERENCES categories(category_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, category_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_categories_category_idx
            ON conversation_categories(category_id);

        CREATE TABLE IF NOT EXISTS tags (
            tag_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_tags (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            tag_id INTEGER NOT NULL REFERENCES tags(tag_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, tag_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_tags_tag_idx
            ON conversation_tags(tag_id);

        CREATE TABLE IF NOT EXISTS work_projects (
            project_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            description TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_work_projects (
            conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id)
                ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES work_projects(project_id)
                ON DELETE CASCADE,
            assigned_at TEXT NOT NULL,
            PRIMARY KEY (conversation_id, project_id)
        );

        CREATE INDEX IF NOT EXISTS conversation_work_projects_project_idx
            ON conversation_work_projects(project_id);
        """
    )
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def connect_database(
    database_path: Path | str,
    *,
    require_current: bool = True,
) -> sqlite3.Connection:
    """Open the archive database and validate/create the current schema."""
    database_path = Path(database_path)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    existing_schema = schema_exists(connection)
    user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    if not existing_schema:
        create_schema(connection)
    elif user_version in {2, 3}:
        LOGGER.info(
            "Migrating SQLite schema from version %d to version %d",
            user_version,
            SCHEMA_VERSION,
        )
        create_schema(connection)
    elif user_version == SCHEMA_VERSION:
        create_schema(connection)
    elif require_current:
        connection.close()
        raise ValueError(
            f"Database schema version is {user_version}, but this code requires "
            f"version {SCHEMA_VERSION}. Run the rebuild command once."
        )

    return connection


def remove_database_files(database_path: Path | str) -> None:
    """Delete SQLite database, WAL and SHM files if present."""
    database_path = Path(database_path)
    for path in (
        database_path,
        Path(str(database_path) + "-wal"),
        Path(str(database_path) + "-shm"),
    ):
        if path.exists():
            LOGGER.info("Deleting %s", path)
            path.unlink()


def delete_message_index_rows(
    connection: sqlite3.Connection,
    conversation_id: str,
) -> None:
    """Delete message and FTS rows for one conversation."""
    old_ids = connection.execute(
        "SELECT id FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchall()
    for old_row in old_ids:
        connection.execute(
            "DELETE FROM messages_fts WHERE rowid = ?",
            (old_row["id"],),
        )
    connection.execute(
        "DELETE FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    )


def get_or_create_category(
    connection: sqlite3.Connection,
    name: str,
) -> sqlite3.Row:
    """Return a category row, creating it when needed."""
    clean_name = normalize_text(name)
    if not clean_name:
        raise ValueError("Category name cannot be empty.")

    row = connection.execute(
        "SELECT category_id, name FROM categories WHERE name = ? COLLATE NOCASE",
        (clean_name,),
    ).fetchone()
    if row:
        return row

    with connection:
        cursor = connection.execute(
            "INSERT INTO categories (name, description, created_at) VALUES (?, NULL, ?)",
            (clean_name, now_iso()),
        )
    row = connection.execute(
        "SELECT category_id, name FROM categories WHERE category_id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    assert row is not None
    return row
