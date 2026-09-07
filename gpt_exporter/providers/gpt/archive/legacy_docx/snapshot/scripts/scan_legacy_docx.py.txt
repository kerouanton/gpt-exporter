import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Audit historical ChatGPT DOCX files without importing them."""

import argparse
import json
import logging
from pathlib import Path

from gpt_exporter.legacy.docx import scan_legacy_directory, scan_legacy_docx


LOGGER = logging.getLogger("gpt_exporter.legacy_docx")


def configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit of historical ChatGPT conversations copied to DOCX. "
            "No archive, database, or source file is modified."
        )
    )
    parser.add_argument("path", type=Path, help="DOCX file or directory to scan")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into subdirectories",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        type=Path,
        help="Write the complete report to this JSON file",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose diagnostic logging",
    )
    return parser


def _reports_for_path(path: Path, *, recursive: bool):
    path = path.expanduser().resolve()
    if path.is_dir():
        return scan_legacy_directory(path, recursive=recursive)
    return [scan_legacy_docx(path)]


def _print_report(report) -> None:
    print(f"File: {report.filename}")
    print(f"  Category hint: {report.category_hint or '-'}")
    print(f"  Filename date: {report.filename_date_hint or '-'}")
    print(f"  DOCX created: {report.docx_created_at or '-'}")
    print(f"  Title hint: {report.filename_title_hint}")
    print(f"  SHA-256: {report.sha256}")
    print(
        "  Structure: "
        f"{report.paragraph_count} paragraphs, "
        f"{report.table_count} tables, "
        f"{report.heading_count} headings"
    )
    print(f"  Boundary candidates: {report.boundary_candidate_count}")
    print(f"  Parse confidence: {report.parse_confidence}")
    if report.likely_first_user_message:
        preview = report.likely_first_user_message
        if len(preview) > 160:
            preview = preview[:157] + "..."
        print(f"  First likely user message: {preview}")
    for note in report.notes:
        print(f"  Note: {note}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.debug)

    reports = _reports_for_path(args.path, recursive=not args.no_recursive)
    LOGGER.debug("Scanned %d DOCX file(s)", len(reports))

    for index, report in enumerate(reports):
        if index:
            print()
        _print_report(report)

    if args.json_path:
        output_path = args.json_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "gpt-exporter-legacy-docx-audit-v1",
            "source_count": len(reports),
            "reports": [report.to_dict() for report in reports],
        }
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
