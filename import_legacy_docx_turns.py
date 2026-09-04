import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Import normalized legacy DOCX turns into the archive SQLite/FTS5 index."""

import argparse
import json
from pathlib import Path

from gpt_exporter.index._legacy_indexer import DEFAULT_DATABASE_PATH
from gpt_exporter.legacy.sqlite_import import (
    LEGACY_SQLITE_IMPORT_VERSION,
    import_legacy_collection,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import normalized legacy DOCX turns into the existing archive index. "
            "Each source DOCX is verified by SHA-256 before indexing."
        )
    )
    parser.add_argument("input", type=Path, help="legacy-docx-turns.json")
    parser.add_argument("--docx-root", type=Path, required=True, help="Directory containing immutable legacy DOCX files")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH, help="Archive SQLite database")
    parser.add_argument("--force", action="store_true", help="Reindex legacy conversations even when SHA-256 is unchanged")
    args = parser.parse_args(argv)

    source = args.input.expanduser().resolve()
    docx_root = args.docx_root.expanduser().resolve()
    database = args.database.expanduser().resolve()
    if not docx_root.is_dir():
        raise FileNotFoundError(docx_root)

    payload = json.loads(source.read_text(encoding="utf-8"))
    counts = import_legacy_collection(
        payload,
        database_path=database,
        docx_root=docx_root,
        force=args.force,
    )

    print(f"Legacy SQLite importer: {LEGACY_SQLITE_IMPORT_VERSION}")
    print(f"Updated conversations: {counts['updated']}")
    print(f"Unchanged conversations: {counts['unchanged']}")
    print(f"Indexed turns: {counts['turns']}")
    print(f"Failed conversations: {counts['failed']}")
    print(f"Database: {database}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
