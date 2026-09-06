import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Rebuild the native ChatGPT archive index and re-import legacy DOCX turns."""

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

from gpt_exporter.index._legacy_indexer import (
    DEFAULT_ARCHIVE_ROOT,
    DEFAULT_DATABASE_PATH,
    DEFAULT_DOWNLOADS_DIR,
    rebuild_index,
)
from gpt_exporter.legacy.sqlite_import import import_legacy_collection, validate_legacy_collection


def _backup_database(database: Path) -> Path | None:
    if not database.is_file():
        return None
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database.with_name(f"{database.stem}-before-rebuild-{timestamp}{database.suffix}")
    shutil.copy2(database, backup)
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the disposable native SQLite/FTS5 index, then restore normalized "
            "legacy DOCX conversations into the rebuilt database."
        )
    )
    parser.add_argument("--archive-root", type=Path, default=DEFAULT_ARCHIVE_ROOT)
    parser.add_argument("--downloads-dir", type=Path, default=DEFAULT_DOWNLOADS_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--legacy-turns", type=Path, required=True, help="legacy-docx-turns.json")
    parser.add_argument("--docx-root", type=Path, required=True, help="Root containing immutable legacy DOCX files")
    parser.add_argument("--apply", action="store_true", help="Actually rebuild. Without this flag only validate inputs.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup of the existing SQLite database")
    args = parser.parse_args(argv)

    archive_root = args.archive_root.expanduser().resolve()
    downloads_dir = args.downloads_dir.expanduser().resolve()
    database = args.database.expanduser().resolve()
    legacy_turns = args.legacy_turns.expanduser().resolve()
    docx_root = args.docx_root.expanduser().resolve()

    if not downloads_dir.is_dir():
        raise FileNotFoundError(downloads_dir)
    if not docx_root.is_dir():
        raise FileNotFoundError(docx_root)
    payload = json.loads(legacy_turns.read_text(encoding="utf-8"))
    validation = validate_legacy_collection(payload, docx_root=docx_root)

    print(f"Validated legacy conversations: {validation['conversations']}")
    print(f"Validated legacy turns: {validation['turns']}")
    print(f"Legacy validation failures: {validation['failed']}")
    if validation["failed"]:
        return 1

    if not args.apply:
        print("Dry-run only: database was not rebuilt. Re-run with --apply to rebuild.")
        print(f"Target database: {database}")
        return 0

    if not args.no_backup:
        backup = _backup_database(database)
        if backup is not None:
            print(f"Database backup: {backup}")

    rebuild_index(downloads_dir, archive_root, database)
    counts = import_legacy_collection(
        payload,
        database_path=database,
        docx_root=docx_root,
        force=True,
    )

    print(f"Legacy conversations restored: {counts['updated']}")
    print(f"Legacy turns restored: {counts['turns']}")
    print(f"Legacy restore failures: {counts['failed']}")
    print(f"Database: {database}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
