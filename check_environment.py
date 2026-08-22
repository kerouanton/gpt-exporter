import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import importlib
import json
import sys
from pathlib import Path

DEBUG = True
ROOT = Path(__file__).resolve().parent
USER_PROFILE = Path(os.environ.get("USERPROFILE") or Path.home())
ARCHIVE_ROOT = USER_PROFILE / "Documents" / "ChatGPT Archive"
WINDOWS_DOWNLOADS = USER_PROFILE / "Downloads"

REQUIRED_FILES = (
    "archive_chats.py",
    "collect_chatgpt_archive.js",
    "import_browser_bundle.py",
    "inventory_media.py",
    "build_asset_manifest.py",
    "export_all.py",
    "audit_asset_references.py",
    "export_markdown.py",
    "export_docx.py",
    "requirements.txt",
)

OPTIONAL_LEGACY_FILES = (
    "download_conversations.py",
    "download_assets.py",
)

REQUIRED_MODULES = {
    "markdown_it": "markdown-it-py",
    "docx": "python-docx",
    "PIL": "Pillow",
}

GENERATED_DIRECTORIES = (
    ARCHIVE_ROOT / "downloads",
    ARCHIVE_ROOT / "assets",
    ARCHIVE_ROOT / "reports",
)

SOURCE_BUNDLE = "chatgpt-archive-source.json"
EXPECTED_BUNDLE_FORMAT = "chatgpt-archive-source-v1"


def debug(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}")


def status(label: str, ok: bool, detail: str | None = None) -> None:
    suffix = f": {detail}" if detail else ""
    print(f"[{'OK' if ok else 'MISSING'}] {label}{suffix}")


def check_python_version() -> int:
    ok = sys.version_info >= (3, 11)
    status("Python 3.11+", ok, sys.version.split()[0])
    return 0 if ok else 1


def check_modules() -> int:
    failures = 0
    for module_name, package_name in REQUIRED_MODULES.items():
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", None)
            status(package_name, True, str(version) if version else None)
        except Exception as exc:
            status(package_name, False, str(exc))
            failures += 1
    return failures


def check_project_files() -> int:
    failures = 0
    for name in REQUIRED_FILES:
        path = ROOT / name
        ok = path.is_file() and path.stat().st_size > 0
        status(name, ok)
        failures += 0 if ok else 1

    for name in OPTIONAL_LEGACY_FILES:
        path = ROOT / name
        if path.is_file():
            print(f"[OPTIONAL] {name} (legacy standalone tool; not used by archive_chats.py)")

    return failures


def ensure_generated_directories() -> int:
    failures = 0
    for path in GENERATED_DIRECTORIES:
        try:
            path.mkdir(parents=True, exist_ok=True)
            status(str(path), True)
        except OSError as exc:
            status(str(path), False, str(exc))
            failures += 1
    return failures


def check_source_bundle() -> None:
    path = WINDOWS_DOWNLOADS / SOURCE_BUNDLE
    if not path.exists():
        print(f"[INFO] {SOURCE_BUNDLE} is not present in: {WINDOWS_DOWNLOADS}")
        print()
        print("Create it as follows:")
        print("  1. Open your web browser and go to https://chatgpt.com/")
        print("  2. Press F12 to open Developer Tools.")
        print("  3. Open the Console tab.")
        print("  4. Copy the complete contents of collect_chatgpt_archive.js.")
        print("  5. Paste the script into the console and run it.")
        print("  6. Leave the downloaded chatgpt-archive-source.json in Windows Downloads.")
        print("  7. Run archive_chats.py; it will process the file there and delete it after success.")
        return

    if not path.is_file() or path.stat().st_size == 0:
        print(f"[WARNING] {SOURCE_BUNDLE} exists but is empty or is not a regular file.")
        return

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"[WARNING] {SOURCE_BUNDLE} is not valid UTF-8 JSON: {exc}")
        return

    bundle_format = data.get("format") if isinstance(data, dict) else None
    conversations = data.get("conversations") if isinstance(data, dict) else None
    conversation_count = len(conversations) if isinstance(conversations, list) else 0

    if bundle_format != EXPECTED_BUNDLE_FORMAT:
        print(
            f"[WARNING] {SOURCE_BUNDLE} has unexpected format: "
            f"{bundle_format!r}"
        )
        return

    print(
        f"[OK] {SOURCE_BUNDLE}: {conversation_count} conversation(s), "
        f"{path.stat().st_size} bytes"
    )


def main() -> int:
    failures = 0

    print(f"Project directory : {ROOT}")
    print(f"Archive directory : {ARCHIVE_ROOT}")
    print(f"Windows Downloads : {WINDOWS_DOWNLOADS}")
    print(f"Python executable : {sys.executable}")
    print(f"Python version    : {sys.version.split()[0]}")
    print()

    print("Runtime")
    print("=======")
    failures += check_python_version()
    failures += check_modules()

    print()
    print("Active pipeline files")
    print("=====================")
    failures += check_project_files()

    print()
    print("Generated directories")
    print("=====================")
    failures += ensure_generated_directories()

    print()
    print("Current browser bundle")
    print("======================")
    check_source_bundle()

    print()
    if failures:
        print(f"Environment check found {failures} problem(s).")
        return 1

    print("Environment check completed successfully.")
    debug("The source bundle is optional during the environment check but required for a normal archive run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
