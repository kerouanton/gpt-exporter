import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Compatibility CLI for the GPT Exporter media inventory library."""

from gpt_exporter.archive.inventory import inventory_media, render_console_summary
from gpt_exporter.paths import default_archive_paths


PATHS = default_archive_paths()
ARCHIVE_ROOT = PATHS.root
INPUT = PATHS.downloads
REPORTS_DIR = PATHS.reports
TXT = REPORTS_DIR / "inventory-media-report.txt"
JS = REPORTS_DIR / "inventory-media-report.json.xz"


def main() -> int:
    # Preserve the v2.8 CLI side effect: the reports directory existed before
    # conversation parsing began, even when a malformed input later failed.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    result = inventory_media(
        INPUT,
        REPORTS_DIR,
        progress=print,
    )

    print()
    print(render_console_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
