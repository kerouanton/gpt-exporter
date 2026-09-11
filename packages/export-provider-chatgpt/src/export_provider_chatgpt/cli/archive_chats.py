import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Compatibility CLI for the GPT Exporter in-process archive pipeline."""

import argparse
import sys
from pathlib import Path

from gpt_exporter.paths import default_archive_paths
from gpt_exporter.pipeline import archive_bundle


ROOT = Path(__file__).resolve().parent
PATHS = default_archive_paths()
ARCHIVE_ROOT = PATHS.root
DOWNLOADS_DIR = PATHS.downloads
ASSETS_DIR = PATHS.assets
REPORTS_DIR = PATHS.reports
MARKDOWN_DIR = PATHS.markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import the browser-generated ChatGPT archive bundle and "
            "create cumulative DOCX exports."
        )
    )
    parser.add_argument(
        "--convert-only",
        action="store_true",
        help="Skip browser import and rebuild DOCX exports from existing JSON/XZ files.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete generated downloads, assets, reports, Markdown, and root DOCX files first.",
    )
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="Do not inventory or download images and attachments.",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()

    try:
        archive_bundle(
            archive_root=ARCHIVE_ROOT,
            convert_only=arguments.convert_only,
            fresh=arguments.fresh,
            skip_assets=arguments.skip_assets,
            legacy_root=ROOT,
            progress=print,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
