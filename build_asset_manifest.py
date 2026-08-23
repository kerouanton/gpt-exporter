import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import sys
from pathlib import Path

from gpt_exporter.archive.manifest import (
    JSON_MANIFEST_NAME,
    TEXT_MANIFEST_NAME,
    NoConversationFilesError,
    build_asset_manifest,
    render_console_summary,
)
from gpt_exporter.paths import default_archive_paths, default_user_profile


ROOT = Path(__file__).resolve().parent
USER_PROFILE = default_user_profile()
PATHS = default_archive_paths()
ARCHIVE_ROOT = PATHS.root
INPUT_DIR = PATHS.downloads
REPORTS_DIR = PATHS.reports
OUTPUT_JSON = REPORTS_DIR / JSON_MANIFEST_NAME
OUTPUT_TXT = REPORTS_DIR / TEXT_MANIFEST_NAME


def main() -> int:
    try:
        result = build_asset_manifest(
            INPUT_DIR,
            REPORTS_DIR,
            progress=print,
        )
    except NoConversationFilesError:
        print(f"No conversation JSON files found in: {INPUT_DIR}")
        return 1

    print()
    print(render_console_summary(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
