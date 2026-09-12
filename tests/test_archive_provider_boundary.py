from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHATGPT_PROVIDER_ROOT = (
    REPOSITORY_ROOT
    / "packages"
    / "export-provider-chatgpt"
    / "src"
    / "export_provider_chatgpt"
)


class ArchiveProviderBoundaryTests(unittest.TestCase):
    def test_chatgpt_archive_analysis_implementations_live_under_provider(self) -> None:
        provider = CHATGPT_PROVIDER_ROOT / "archive"
        for name in ("audit.py", "inventory.py", "manifest.py"):
            self.assertTrue((provider / name).is_file())

    def test_importing_archive_package_does_not_load_gpt_provider(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            import gpt_exporter.archive
            assert not any(
                name == "gpt_exporter.providers.gpt"
                or name.startswith("gpt_exporter.providers.gpt.")
                for name in sys.modules
            )
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_importing_archive_compatibility_modules_is_provider_lazy(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            import gpt_exporter.archive.audit
            import gpt_exporter.archive.importer
            import gpt_exporter.archive.inventory
            import gpt_exporter.archive.manifest
            assert not any(
                name == "gpt_exporter.providers.gpt"
                or name.startswith("gpt_exporter.providers.gpt.")
                for name in sys.modules
            )
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
