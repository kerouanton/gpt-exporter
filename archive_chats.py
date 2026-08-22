import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import argparse
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
DOWNLOADS_DIR = ARCHIVE_ROOT / "downloads"
ASSETS_DIR = ARCHIVE_ROOT / "assets"
MARKDOWN_DIR = ARCHIVE_ROOT / "markdown"
DOCX_DIR = ARCHIVE_ROOT
LEGACY_EXPORTS_DIR = ARCHIVE_ROOT / "exports"
LEGACY_MARKDOWN_DIR = LEGACY_EXPORTS_DIR / "markdown"
LEGACY_DOCX_DIR = LEGACY_EXPORTS_DIR / "docx"
REPORTS_DIR = ARCHIVE_ROOT / "reports"
SOURCE_BUNDLE_NAME = "chatgpt-archive-source.json"

GENERATED_DIRECTORIES = (
    DOWNLOADS_DIR,
    ASSETS_DIR,
    REPORTS_DIR,
)

LEGACY_DATA_DIRECTORIES = (
    "downloads",
    "assets",
    "exports",
    "reports",
)


def run_step(label: str, script: str, arguments: list[str] | None = None) -> None:
    command = [sys.executable, str(ROOT / script), *(arguments or [])]
    print()
    print("=" * 72)
    print(label)
    print("=" * 72)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Step failed with exit code {completed.returncode}: {label}"
        )


def clear_generated_data() -> None:
    for directory in GENERATED_DIRECTORIES:
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)

    for directory in (MARKDOWN_DIR, LEGACY_EXPORTS_DIR):
        if directory.exists():
            shutil.rmtree(directory)

    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    for docx_path in ARCHIVE_ROOT.glob("*.docx"):
        docx_path.unlink()


def migrate_legacy_archive() -> None:
    """Move the old in-project data tree to the Windows Documents archive root.

    Migration is intentionally conservative. A directory is moved only when the
    legacy source exists and the matching destination does not. If both exist,
    the program stops rather than merging or overwriting archival data.
    """
    conflicts: list[tuple[Path, Path]] = []

    for name in LEGACY_DATA_DIRECTORIES:
        source = ROOT / name
        destination = ARCHIVE_ROOT / name

        if not source.exists():
            continue

        if destination.exists():
            destination_has_data = (
                not destination.is_dir()
                or any(
                    item.is_file() or item.is_symlink()
                    for item in destination.rglob("*")
                )
            )
            if destination_has_data:
                conflicts.append((source, destination))
                continue

            shutil.rmtree(destination)

        ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
        print()
        print(f"Migrating legacy archive directory: {source}")
        print(f"                               -> {destination}")
        shutil.move(str(source), str(destination))

    if conflicts:
        details = "\n".join(
            f"  legacy: {source}\n  target: {destination}"
            for source, destination in conflicts
        )
        raise RuntimeError(
            "Archive data exists both inside the project and under Documents. "
            "Automatic migration was stopped to avoid overwriting data.\n"
            f"{details}"
        )




def migrate_output_layout() -> None:
    """Move legacy DOCX exports to the archive root and discard legacy Markdown."""
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)

    legacy_docx_files = (
        sorted(LEGACY_DOCX_DIR.glob("*.docx"))
        if LEGACY_DOCX_DIR.is_dir()
        else []
    )

    conflicts: list[tuple[Path, Path]] = []
    duplicates: set[Path] = set()
    for source in legacy_docx_files:
        destination = ARCHIVE_ROOT / source.name
        if not destination.exists():
            continue
        if destination.read_bytes() == source.read_bytes():
            duplicates.add(source)
        else:
            conflicts.append((source, destination))

    if conflicts:
        details = "\n".join(
            f"  legacy: {source}\n  target: {destination}"
            for source, destination in conflicts
        )
        raise RuntimeError(
            "DOCX files exist both in the legacy exports directory and at the "
            "archive root with different contents. Migration was stopped before "
            "moving or deleting output files.\n"
            f"{details}"
        )

    for source in legacy_docx_files:
        destination = ARCHIVE_ROOT / source.name
        if source in duplicates:
            source.unlink()
            print(f"Removed duplicate legacy DOCX: {source}")
            continue
        source.replace(destination)
        print(f"Moved legacy DOCX: {source.name} -> {destination}")

    if LEGACY_MARKDOWN_DIR.exists():
        shutil.rmtree(LEGACY_MARKDOWN_DIR)
        print(f"Removed legacy Markdown directory: {LEGACY_MARKDOWN_DIR}")

    for directory in (LEGACY_DOCX_DIR, LEGACY_EXPORTS_DIR):
        if directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass


def windows_download_directories() -> list[Path]:
    candidates: list[Path] = []

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Downloads")

    home_drive = os.environ.get("HOMEDRIVE")
    home_path = os.environ.get("HOMEPATH")
    if home_drive and home_path:
        candidates.append(Path(f"{home_drive}{home_path}") / "Downloads")

    candidates.append(Path.home() / "Downloads")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def compress_json_file_transactionally(source: Path) -> Path:
    destination = source.with_name(source.name + ".xz")
    raw = source.read_bytes()

    if destination.is_file():
        try:
            with lzma.open(destination, "rb") as handle:
                existing = handle.read()
        except (OSError, EOFError, lzma.LZMAError) as exc:
            raise RuntimeError(f"Unable to verify existing XZ file: {destination}: {exc}") from exc
        if existing != raw:
            raise RuntimeError(
                "Both JSON and XZ versions exist with different contents: "
                f"{source.name} / {destination.name}"
            )
        source.unlink()
        return destination

    temp = destination.with_name(destination.name + ".tmp")
    try:
        with lzma.open(temp, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
            handle.write(raw)
        with lzma.open(temp, "rb") as handle:
            verified = handle.read()
        if verified != raw:
            raise RuntimeError(f"XZ verification failed: {source}")
        temp.replace(destination)
        source.unlink()
    finally:
        if temp.exists():
            temp.unlink()

    print(f"Compressed legacy JSON: {source.name} -> {destination.name}")
    return destination


def migrate_json_storage() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    legacy_conversations = sorted(
        path for path in DOWNLOADS_DIR.glob("*.json")
        if path.name != "download-index.json"
    )
    for source in legacy_conversations:
        compress_json_file_transactionally(source)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in (
        "asset-download-index-v2.json",
        "asset-manifest.json",
        "inventory-media-report.json",
    ):
        source = REPORTS_DIR / name
        if source.is_file():
            compress_json_file_transactionally(source)


def find_source_bundle_in_downloads(name: str) -> Path | None:
    matches: list[Path] = []
    for directory in windows_download_directories():
        candidate = directory / name
        if candidate.is_file() and candidate.stat().st_size > 0:
            matches.append(candidate)

    if not matches:
        return None

    source = max(matches, key=lambda path: path.stat().st_mtime)
    print()
    print(f"Found browser bundle in Windows Downloads: {source}")
    print("The bundle will be processed in place and deleted after a successful run.")
    return source


def print_bundle_creation_instructions() -> None:
    print()
    print("To generate chatgpt-archive-source.json:")
    print("  1. Open your web browser and go to https://chatgpt.com/")
    print("  2. Press F12 to open Developer Tools.")
    print("  3. Open the Console tab.")
    print("  4. Copy the complete contents of collect_chatgpt_archive.js.")
    print("  5. Paste the script into the console and run it.")
    print("  6. Leave the downloaded chatgpt-archive-source.json in Windows Downloads,")
    print("     then run archive_chats.py again. It will process the file in place.")


def require_source_bundle() -> Path:
    path = find_source_bundle_in_downloads(SOURCE_BUNDLE_NAME)
    if path is None:
        print_bundle_creation_instructions()
        searched = ", ".join(str(path) for path in windows_download_directories())
        raise FileNotFoundError(
            f"Required file is missing or empty: {SOURCE_BUNDLE_NAME}. "
            f"Searched Windows Downloads locations: {searched}"
        )
    return path


def delete_consumed_source_bundle(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        print()
        print(f"WARNING: archive succeeded, but the source bundle could not be deleted: {path}")
        print(f"WARNING: {exc}")
        return

    print()
    print(f"Deleted consumed browser bundle: {path}")





def main() -> int:
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
    args = parser.parse_args()

    source_bundle: Path | None = None

    try:
        if args.fresh:
            clear_generated_data()
        else:
            migrate_legacy_archive()
            for directory in GENERATED_DIRECTORIES:
                directory.mkdir(parents=True, exist_ok=True)

        migrate_output_layout()
        migrate_json_storage()

        if not args.convert_only:
            source_bundle = require_source_bundle()
            run_step(
                "1/4 - Import browser archive bundle",
                "import_browser_bundle.py",
                [str(source_bundle)],
            )

        json_files = sorted(DOWNLOADS_DIR.glob("*.json.xz"))
        if not json_files:
            json_files = [
                path for path in DOWNLOADS_DIR.glob("*.json")
                if path.name != "download-index.json"
            ]
        if not json_files:
            raise FileNotFoundError(
                "No conversation JSON/XZ files were found in the downloads directory."
            )

        if not args.skip_assets:
            run_step("2/4 - Inventory media references", "inventory_media.py")
            run_step("3/4 - Build asset manifest", "build_asset_manifest.py")
        else:
            print("\nAssets skipped by request.")

        export_arguments = ["--overwrite-all"]
        if not args.convert_only:
            export_arguments.extend([
                "--batch-file",
                str(REPORTS_DIR / "current-batch.json"),
            ])

        batch_file = REPORTS_DIR / "current-batch.json"
        skip_export = False
        if not args.convert_only and batch_file.is_file():
            import json
            batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
            if not batch_data.get("conversation_files"):
                print("\nNo new or larger conversations to export.")
                print("Existing local archive was preserved.")
                skip_export = True

        if not skip_export:
            run_step(
                "4/4 - Export new or larger conversations",
                "export_all.py",
                export_arguments,
            )

    except (FileNotFoundError, RuntimeError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1

    if source_bundle is not None:
        delete_consumed_source_bundle(source_bundle)

    print()
    print("Archive completed successfully.")
    print(f"Archive root: {ARCHIVE_ROOT}")
    print(f"DOCX files : {ARCHIVE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
