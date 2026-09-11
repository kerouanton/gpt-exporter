import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import sys
from pathlib import Path

from gpt_exporter.archive.audit import (
    ASSET_ID_ANY_PATTERN,
    ASSET_REFERENCE_PATTERN,
    LOCAL_ASSET_ID_PATTERN,
    SKIP_SUFFIXES,
    DEFAULT_REPORT_NAME,
    active_node_ids,
    audit_asset_references,
    classify_unreferenced,
    collect_archive_occurrences,
    collect_asset_audit,
    collect_local_assets,
    describe_duplicate,
    docx_asset_references,
    duplicate_kind,
    extract_ids_from_value,
    local_asset_id,
    markdown_asset_references,
    paragraph_texts_from_xml,
    scan_outputs,
    sha256_file,
    write_report,
)
from gpt_exporter.paths import default_archive_paths, default_user_profile


DEBUG = False
USER_PROFILE = default_user_profile()
DEFAULT_ARCHIVE_ROOT = default_archive_paths().root


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the cumulative ChatGPT archive and warn when a local "
            "asset is not represented by an Asset ID provenance marker in "
            "any generated DOCX or persistent Markdown file."
        )
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=DEFAULT_ARCHIVE_ROOT,
        help="Archive root. Default: %USERPROFILE%\\Documents\\ChatGPT Archive",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Return exit code 2 when unreferenced local assets or output "
            "references to missing local assets are found."
        ),
    )
    return parser.parse_args()


def print_warning_ids(title: str, items: list[dict[str, object]]) -> None:
    if not items:
        return

    print()
    print(f"WARNING: {title}: {len(items)}")
    for item in items[:20]:
        file_id = str(item.get("file_id") or "unknown")
        paths = item.get("paths")
        if isinstance(paths, list) and paths:
            print(f"  {file_id} -> {paths[0]}")
        else:
            print(f"  {file_id}")
    if len(items) > 20:
        print(f"  ... and {len(items) - 20} more; see the audit report.")


def main() -> int:
    arguments = parse_arguments()
    archive_root = arguments.archive_root.expanduser().resolve()

    if not archive_root.is_dir():
        print(f"ERROR: archive root not found: {archive_root}")
        return 1

    result = audit_asset_references(archive_root)
    report = result.report

    unreferenced = report.get("unreferenced_local_assets", [])
    if not isinstance(unreferenced, list):
        unreferenced = []
    missing_local = report.get("referenced_missing_local_assets", [])
    if not isinstance(missing_local, list):
        missing_local = []
    duplicates = report.get("duplicate_local_asset_ids", [])
    if not isinstance(duplicates, list):
        duplicates = []
    unidentified_files = report.get("unidentified_local_asset_files", [])
    if not isinstance(unidentified_files, list):
        unidentified_files = []
    duplicate_status_counts = report.get(
        "duplicate_local_asset_content_status_counts",
        {},
    )
    if not isinstance(duplicate_status_counts, dict):
        duplicate_status_counts = {}
    duplicate_kind_counts = report.get("duplicate_local_asset_kind_counts", {})
    if not isinstance(duplicate_kind_counts, dict):
        duplicate_kind_counts = {}
    unreferenced_category_counts = report.get("unreferenced_category_counts", {})
    if not isinstance(unreferenced_category_counts, dict):
        unreferenced_category_counts = {}

    print()
    print("Asset reference audit")
    print("=====================")
    print(f"Archive root               : {archive_root}")
    print(f"Physical asset files       : {report.get('asset_files_scanned', 0)}")
    print(f"Unique local asset IDs     : {report.get('unique_local_asset_ids', 0)}")
    print(f"DOCX files scanned         : {report.get('docx_files_scanned', 0)}")
    print(f"Markdown files scanned     : {report.get('markdown_files_scanned', 0)}")
    print(f"Rendered asset IDs found   : {report.get('referenced_asset_ids', 0)}")
    print(f"Unreferenced local assets  : {len(unreferenced)}")
    print(f"Referenced but local-missing: {len(missing_local)}")
    print(f"Duplicate local asset IDs  : {len(duplicates)}")
    print(
        "  byte-identical           : "
        f"{duplicate_status_counts.get('identical', 0)}"
    )
    print(
        "  content-conflicting      : "
        f"{duplicate_status_counts.get('conflicting', 0)}"
    )
    print(
        "  unreadable               : "
        f"{duplicate_status_counts.get('unreadable', 0)}"
    )
    if duplicate_kind_counts:
        print("Duplicate local asset kinds")
        for kind, count in duplicate_kind_counts.items():
            print(f"  {kind:27s}: {count:5d}")
    print(f"Unidentified asset files   : {len(unidentified_files)}")
    print(f"Report                     : {result.report_path}")
    if unreferenced_category_counts:
        print()
        print("Unreferenced asset classification")
        print("---------------------------------")
        for category, count in sorted(unreferenced_category_counts.items()):
            print(f"  {category:27s}: {count:5d}")

    print_warning_ids(
        "downloaded/local assets not referenced by any DOCX or persistent Markdown",
        unreferenced,
    )
    print_warning_ids(
        "assets referenced by output but missing from the local asset corpus",
        [
            {
                "file_id": item["file_id"],
                "paths": item["referenced_by"],
            }
            for item in missing_local
            if isinstance(item, dict)
        ],
    )

    if unidentified_files:
        print()
        print(
            "WARNING: local asset files without a recognized file/external ID: "
            f"{len(unidentified_files)}"
        )
        for relative in unidentified_files[:20]:
            print(f"  {relative}")
        if len(unidentified_files) > 20:
            print(
                f"  ... and {len(unidentified_files) - 20} more; "
                "see the audit report."
            )

    conflicting_duplicates = [
        item
        for item in duplicates
        if isinstance(item, dict)
        and item.get("content_status") == "conflicting"
    ]
    if conflicting_duplicates:
        print()
        print(
            "WARNING: duplicate local asset IDs with different byte content: "
            f"{len(conflicting_duplicates)}"
        )
        for item in conflicting_duplicates[:20]:
            print(f"  {item['file_id']}")
            for relative in item.get("paths", []):
                print(f"    {relative}")

    if not unreferenced and not missing_local and not unidentified_files:
        print()
        print("Asset reference audit completed with no discrepancies.")

    if arguments.strict and (
        unreferenced or missing_local or unidentified_files
    ):
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
