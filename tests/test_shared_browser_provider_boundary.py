from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SharedBrowserProviderBoundaryTests(unittest.TestCase):
    def test_shared_browser_imports_without_gpt_provider_or_root_facades(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_package = REPOSITORY_ROOT / "gpt_exporter"
            target_package = temporary_root / "gpt_exporter"
            shutil.copytree(source_package, target_package)
            shutil.rmtree(target_package / "providers" / "gpt", ignore_errors=True)

            script = "\n".join(
                [
                    "import sys",
                    "from pathlib import Path",
                    "from gpt_exporter.ui.browser import archive_core, archive_browser",
                    "assert archive_browser.core is archive_core",
                    "assert 'gpt_exporter.providers.gpt' not in sys.modules",
                    "package = Path(__import__('gpt_exporter').__file__).resolve().parent",
                    "assert not (package / 'providers' / 'gpt').exists()",
                    "assert package / 'ui' / 'browser' in Path(archive_browser.__file__).resolve().parents",
                ]
            )

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(temporary_root)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=temporary_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
