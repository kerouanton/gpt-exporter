import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Verify imported legacy DOCX conversations and optionally run an FTS search."""

import argparse
import sqlite3
from pathlib import Path

from gpt_exporter.index._legacy_indexer import DEFAULT_DATABASE_PATH, make_fts_query


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify legacy DOCX rows in the archive SQLite/FTS5 index")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--query", default="", help="Optional FTS query to test against imported legacy turns")
    args = parser.parse_args(argv)

    database = args.database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(database)

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        provenance_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_conversation_sources'"
        ).fetchone()
        if not provenance_table:
            print("Legacy provenance table: missing")
            return 1

        conversations = connection.execute(
            "SELECT COUNT(*) AS n FROM legacy_conversation_sources"
        ).fetchone()["n"]
        turns = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM messages AS m
            JOIN legacy_conversation_sources AS l
              ON l.conversation_id = m.conversation_id
            """
        ).fetchone()["n"]
        fts_rows = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM messages_fts AS f
            JOIN legacy_conversation_sources AS l
              ON l.conversation_id = f.conversation_id
            """
        ).fetchone()["n"]

        print(f"Legacy conversations in SQLite: {conversations}")
        print(f"Legacy turns in messages: {turns}")
        print(f"Legacy turns in FTS5: {fts_rows}")

        if args.query.strip():
            rows = connection.execute(
                """
                SELECT DISTINCT f.conversation_id, f.title, f.author_role,
                       snippet(messages_fts, 0, '[', ']', ' … ', 18) AS excerpt
                FROM messages_fts AS f
                JOIN legacy_conversation_sources AS l
                  ON l.conversation_id = f.conversation_id
                WHERE messages_fts MATCH ?
                ORDER BY f.title COLLATE NOCASE
                LIMIT 20
                """,
                (make_fts_query(args.query),),
            ).fetchall()
            print(f"Legacy FTS matches for {args.query!r}: {len(rows)}")
            for row in rows:
                print(f"- {row['title']} [{row['author_role']}] :: {row['excerpt']}")

        return 0 if conversations > 0 and turns == fts_rows else 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
