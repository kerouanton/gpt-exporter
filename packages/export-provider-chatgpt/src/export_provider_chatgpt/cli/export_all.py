import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import sys
from pathlib import Path

from gpt_exporter.export.batch import (
    DOWNLOAD_DIRECTORY,
    PERSISTENT_MARKDOWN_DIRECTORY,
    conversation_docx_name,
    conversation_markdown_name,
    export_batch,
)
from gpt_exporter.paths import default_archive_paths


MARKDOWN_EXPORTER = "gpt_exporter.export.markdown"
DOCX_EXPORTER = "gpt_exporter.export.docx"
ASSET_AUDITOR = "gpt_exporter.archive.audit"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert ChatGPT JSON/XZ files to DOCX. Markdown is temporary by "
            "default and is removed after a successful conversion."
        )
    )
    parser.add_argument(
        "--batch-file",
        type=Path,
        default=None,
        help=(
            "JSON file containing a conversation_files list. "
            "Only those conversation files are converted."
        ),
    )
    parser.add_argument(
        "--overwrite-markdown",
        action="store_true",
        help="Regenerate persistent Markdown when --markdown-only or --keep-markdown is used.",
    )
    parser.add_argument(
        "--overwrite-docx",
        action="store_true",
        help="Regenerate DOCX files even when a non-empty output file already exists.",
    )
    parser.add_argument(
        "--overwrite-all",
        action="store_true",
        help="Regenerate both intermediate Markdown and DOCX files.",
    )
    parser.add_argument(
        "--markdown-only",
        action="store_true",
        help=(
            "Generate and keep Markdown files in ChatGPT Archive\\markdown; "
            "do not create DOCX files."
        ),
    )
    parser.add_argument(
        "--keep-markdown",
        action="store_true",
        help=(
            "Keep Markdown files in ChatGPT Archive\\markdown after DOCX conversion. "
            "By default Markdown is temporary."
        ),
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    project_directory = Path(__file__).resolve().parent

    batch_path = arguments.batch_file
    if batch_path is not None and not batch_path.is_absolute():
        batch_path = (project_directory / batch_path).resolve()

    try:
        result = export_batch(
            archive_root=default_archive_paths().root,
            batch_file=batch_path,
            overwrite_markdown=arguments.overwrite_markdown,
            overwrite_docx=arguments.overwrite_docx,
            overwrite_all=arguments.overwrite_all,
            markdown_only=arguments.markdown_only,
            keep_markdown=arguments.keep_markdown,
            progress=print,
        )
        return 0 if result.success else 1
    except KeyboardInterrupt:
        print("ERROR: operation cancelled by user.")
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
