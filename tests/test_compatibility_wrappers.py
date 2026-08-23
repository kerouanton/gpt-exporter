import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CompatibilityWrapperTests(unittest.TestCase):
    def test_root_compatibility_scripts_delegate_to_package_implementations(self) -> None:
        expectations = {
            "import_browser_bundle": (
                "gpt_exporter.archive._legacy_importer",
                "import_bundle",
            ),
            "export_markdown": (
                "gpt_exporter.export._legacy_markdown",
                "reconstruct_active_path",
            ),
            "export_docx": (
                "gpt_exporter.export._legacy_docx",
                "convert_markdown_to_docx",
            ),
            "index_chatgpt_archive": (
                "gpt_exporter.index._legacy_indexer",
                "normalize_text",
            ),
        }

        for module_name, (implementation_name, public_name) in expectations.items():
            with self.subTest(module=module_name):
                script = (
                    f"import {module_name} as wrapper; "
                    f"assert wrapper._implementation.__name__ == {implementation_name!r}; "
                    f"assert getattr(wrapper, {public_name!r}) is "
                    f"getattr(wrapper._implementation, {public_name!r})"
                )
                completed = subprocess.run(
                    [sys.executable, "-c", script],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(
                    completed.stdout,
                    f"The filename of this script is: {module_name}.py\n",
                )

    def test_root_compatibility_clis_keep_help_entry_points(self) -> None:
        for script_name in (
            "import_browser_bundle.py",
            "export_markdown.py",
            "export_docx.py",
            "index_chatgpt_archive.py",
        ):
            with self.subTest(script=script_name):
                completed = subprocess.run(
                    [sys.executable, str(REPOSITORY_ROOT / script_name), "--help"],
                    cwd=REPOSITORY_ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(
                    completed.stdout.startswith(
                        f"The filename of this script is: {script_name}\n"
                    ),
                    completed.stdout,
                )
                self.assertNotIn("_legacy_", completed.stdout)
                self.assertIn("usage:", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
