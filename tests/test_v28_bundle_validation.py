import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "characterization"
IMPORT_SCRIPT = PROJECT_ROOT / "import_browser_bundle.py"


class V28BundleValidationCharacterizationTests(unittest.TestCase):
    def test_invalid_bundle_format_fails_without_creating_archive_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            bundle = profile / "invalid.json"
            bundle.write_bytes((FIXTURE_ROOT / "bundle_invalid.json").read_bytes())

            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)
            completed = subprocess.run(
                [sys.executable, str(IMPORT_SCRIPT), str(bundle)],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            archive_root = profile / "Documents" / "ChatGPT Archive"
            self.assertFalse((archive_root / "downloads").exists())
            self.assertFalse((archive_root / "assets").exists())
            self.assertFalse((archive_root / "reports").exists())

    def test_missing_bundle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = Path(temporary_directory)
            missing_bundle = profile / "missing.json"
            environment = os.environ.copy()
            environment["USERPROFILE"] = str(profile)

            completed = subprocess.run(
                [sys.executable, str(IMPORT_SCRIPT), str(missing_bundle)],
                cwd=PROJECT_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
