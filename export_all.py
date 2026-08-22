import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import ModuleType


MARKDOWN_EXPORTER = "export_markdown.py"
DOCX_EXPORTER = "export_docx.py"
ASSET_AUDITOR = "audit_asset_references.py"
DOWNLOAD_DIRECTORY = "downloads"
PERSISTENT_MARKDOWN_DIRECTORY = "markdown"


def load_module(module_name: str, script_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Python module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_main(module: ModuleType, arguments: list[str]) -> int:
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(Path(module.__file__).resolve()), *arguments]
        result = module.main()
        return int(result or 0)
    finally:
        sys.argv = old_argv


def conversation_markdown_name(json_path: Path) -> str:
    if json_path.name.lower().endswith(".json.xz"):
        return json_path.name[:-8] + ".md"
    return json_path.with_suffix(".md").name


def conversation_docx_name(json_path: Path) -> str:
    return Path(conversation_markdown_name(json_path)).with_suffix(".docx").name


def main() -> int:
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
    arguments = parser.parse_args()

    project_directory = Path(__file__).resolve().parent
    user_profile = Path(os.environ.get("USERPROFILE") or Path.home())
    archive_root = user_profile / "Documents" / "ChatGPT Archive"
    download_directory = archive_root / DOWNLOAD_DIRECTORY
    persistent_markdown_directory = archive_root / PERSISTENT_MARKDOWN_DIRECTORY
    markdown_exporter_path = project_directory / MARKDOWN_EXPORTER
    docx_exporter_path = project_directory / DOCX_EXPORTER
    asset_auditor_path = project_directory / ASSET_AUDITOR

    for required_path in (
        markdown_exporter_path,
        asset_auditor_path,
        download_directory,
    ):
        if not required_path.exists():
            print(f"ERROR: missing path: {required_path}")
            return 1

    if arguments.batch_file is not None:
        batch_path = arguments.batch_file
        if not batch_path.is_absolute():
            batch_path = (project_directory / batch_path).resolve()
        if not batch_path.is_file():
            print(f"ERROR: batch file not found: {batch_path}")
            return 1

        batch_data = json.loads(batch_path.read_text(encoding="utf-8"))
        batch_names = batch_data.get("conversation_files", [])
        if not isinstance(batch_names, list):
            print("ERROR: invalid conversation_files in batch file")
            return 1

        json_files: list[Path] = []
        for name in batch_names:
            if not isinstance(name, str):
                continue
            candidate = download_directory / Path(name).name
            if candidate.is_file():
                json_files.append(candidate)
            else:
                print(f"WARNING: batch JSON not found: {candidate.name}")
        json_files.sort()
    else:
        json_files = sorted(download_directory.glob("*.json.xz"))
        if not json_files:
            json_files = sorted(
                path
                for path in download_directory.glob("*.json")
                if path.name != "download-index.json"
            )

    if not json_files:
        print(f"ERROR: no JSON files found in {download_directory}")
        return 1

    keep_markdown = arguments.markdown_only or arguments.keep_markdown
    temporary_markdown_directory: Path | None = None

    if keep_markdown:
        markdown_directory = persistent_markdown_directory
        markdown_directory.mkdir(parents=True, exist_ok=True)
        print(f"Persistent Markdown directory: {markdown_directory}")
    else:
        temporary_markdown_directory = Path(
            tempfile.mkdtemp(prefix="gpt-exporter-markdown-")
        )
        markdown_directory = temporary_markdown_directory
        print(f"Temporary Markdown directory: {markdown_directory}")

    print(f"Loading Markdown exporter in-process: {markdown_exporter_path.name}")
    markdown_module = load_module(
        "chatgpt_markdown_exporter",
        markdown_exporter_path,
    )

    requested = len(json_files)
    converted = 0
    skipped = 0
    failed: list[Path] = []

    print()
    print("Markdown intermediate export")
    print("============================")
    print(f"JSON files: {requested}")

    for index, json_path in enumerate(json_files, start=1):
        markdown_path = markdown_directory / conversation_markdown_name(json_path)
        print()
        print(f"[{index}/{requested}] {json_path.name}")

        overwrite_markdown = arguments.overwrite_markdown or arguments.overwrite_all
        if (
            keep_markdown
            and not overwrite_markdown
            and markdown_path.is_file()
            and markdown_path.stat().st_size > 0
        ):
            print(f"SKIP: {markdown_path.name}")
            skipped += 1
            continue

        try:
            return_code = call_main(
                markdown_module,
                [str(json_path), "--output", str(markdown_path)],
            )
        except Exception as exc:
            print(f"FAILED: {json_path.name}: {exc}")
            failed.append(json_path)
            continue

        if return_code == 0:
            converted += 1
        else:
            failed.append(json_path)

    print()
    print("Markdown summary")
    print("================")
    print(f"Requested : {requested}")
    print(f"Converted : {converted}")
    print(f"Skipped   : {skipped}")
    print(f"Failed    : {len(failed)}")

    if failed:
        print()
        print("Failed JSON files")
        print("-----------------")
        for path in failed:
            print(path.name)

    if arguments.markdown_only:
        if failed:
            return 1

        print()
        print("Running cumulative asset reference audit...")
        audit_module = load_module(
            "chatgpt_asset_reference_auditor",
            asset_auditor_path,
        )
        audit_result = call_main(audit_module, [])
        return 0 if audit_result == 0 else 1

    if not docx_exporter_path.exists():
        print(f"ERROR: missing DOCX exporter: {docx_exporter_path}")
        return 1

    print()
    print(f"Loading DOCX exporter in-process: {docx_exporter_path.name}")
    docx_module = load_module("chatgpt_docx_exporter", docx_exporter_path)

    print()
    print("DOCX batch export")
    print("=================")

    docx_return_code = 0
    for json_path in json_files:
        markdown_path = markdown_directory / conversation_markdown_name(json_path)
        if not markdown_path.is_file():
            print(f"FAILED: Markdown missing for DOCX: {markdown_path.name}")
            docx_return_code = 1
            continue

        docx_path = archive_root / conversation_docx_name(json_path)
        docx_arguments = [
            str(markdown_path),
            "--output",
            str(docx_path),
        ]
        if arguments.overwrite_docx or arguments.overwrite_all:
            docx_arguments.append("--overwrite")

        try:
            result = call_main(docx_module, docx_arguments)
            if result != 0:
                docx_return_code = 1
        except Exception as exc:
            print(f"DOCX failed: {markdown_path.name}: {exc}")
            docx_return_code = 1

    success = not failed and docx_return_code == 0

    if success:
        print()
        print("Running cumulative asset reference audit...")
        try:
            audit_module = load_module(
                "chatgpt_asset_reference_auditor",
                asset_auditor_path,
            )
            audit_result = call_main(audit_module, [])
            if audit_result != 0:
                print(
                    "ERROR: asset reference audit could not complete "
                    f"successfully (exit code {audit_result})."
                )
                success = False
        except Exception as exc:
            print(f"ERROR: asset reference audit failed: {exc}")
            success = False

    if temporary_markdown_directory is not None:
        if success:
            shutil.rmtree(temporary_markdown_directory, ignore_errors=False)
            print()
            print(f"Removed temporary Markdown directory: {temporary_markdown_directory}")
        else:
            print()
            print(
                "WARNING: DOCX conversion did not fully succeed. Temporary Markdown "
                f"was preserved for diagnosis: {temporary_markdown_directory}"
            )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
