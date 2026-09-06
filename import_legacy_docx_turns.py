import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Import normalized legacy DOCX turns into the archive SQLite/FTS5 index."""

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

from gpt_exporter.index._legacy_indexer import DEFAULT_DATABASE_PATH
from gpt_exporter.legacy.sqlite_import import (
    LEGACY_SQLITE_IMPORT_VERSION,
    import_legacy_collection,
    validate_legacy_collection,
)


def _backup_database(database: Path) -> Path | None:
    """Copy an existing SQLite file before an --apply import."""
    if not database.is_file():
        return None
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database.with_name(f"{database.stem}-before-legacy-{timestamp}{database.suffix}")
    shutil.copy2(database, backup)
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and optionally import normalized legacy DOCX turns into the "
            "existing archive index. Dry-run is the default; use --apply to write."
        )
    )
    parser.add_argument("input", type=Path, help="legacy-docx-turns.json")
    parser.add_argument("--docx-root", type=Path, required=True, help="Directory containing immutable legacy DOCX files")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH, help="Archive SQLite database")
    parser.add_argument("--apply", action="store_true", help="Actually write legacy conversations into SQLite/FTS5")
    parser.add_argument("--force", action="store_true", help="Reindex legacy conversations even when SHA-256 is unchanged")
    parser.add_argument("--no-backup", action="store_true", help="Skip the automatic pre-import SQLite backup")
    args = parser.parse_args(argv)

    source = args.input.expanduser().resolve()
    docx_root = args.docx_root.expanduser().resolve()
    database = args.database.expanduser().resolve()
    if not docx_root.is_dir():
        raise FileNotFoundError(docx_root)

    payload = json.loads(source.read_text(encoding="utf-8"))
    validation = validate_legacy_collection(payload, docx_root=docx_root)

    print(f"Legacy SQLite importer: {LEGACY_SQLITE_IMPORT_VERSION}")
    print(f"Validated conversations: {validation['conversations']}")
    print(f"Validated turns: {validation['turns']}")
    print(f"Validation failures: {validation['failed']}")

    if not args.apply:
        print("Dry-run only: SQLite was not modified. Re-run with --apply to import.")
        print(f"Target database: {database}")
        return 0

    if not args.no_backup:
        backup = _backup_database(database)
        if backup is not None:
            print(f"Database backup: {backup}")

    counts = import_legacy_collection(
        payload,
        database_path=database,
        docx_root=docx_root,
        force=args.force,
    )
    print(f"Updated conversations: {counts['updated']}")
    print(f"Unchanged conversations: {counts['unchanged']}")
    print(f"Indexed turns: {counts['turns']}")
    print(f"Failed conversations: {counts['failed']}")
    print(f"Database: {database}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
