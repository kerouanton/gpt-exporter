import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PackageClosureTests(unittest.TestCase):
    def test_core_package_loads_without_repository_root_modules(self) -> None:
        """Exercise packaged implementations from package-only imports."""

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_package = REPOSITORY_ROOT / "gpt_exporter"
            target_package = temporary_root / "gpt_exporter"

            import shutil

            shutil.copytree(source_package, target_package)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(temporary_root)

            script = "\n".join(
                [
                    "import importlib.util",
                    "import sys",
                    "assert importlib.util.find_spec('import_browser_bundle') is None",
                    "assert importlib.util.find_spec('export_markdown') is None",
                    "assert importlib.util.find_spec('export_docx') is None",
                    "assert importlib.util.find_spec('index_chatgpt_archive') is None",
                    "import gpt_exporter.pipeline",
                    "from gpt_exporter.archive import importer",
                    "from gpt_exporter.export import markdown, docx",
                    "from gpt_exporter.index import engine",
                    "from gpt_exporter.providers.gpt.importer import _bundle_importer",
                    "from gpt_exporter.providers.gpt import indexing",
                    "from gpt_exporter.providers.gpt.export import markdown as gpt_markdown",
                    "from gpt_exporter.providers.gpt.resources import collector_path",
                    "assert callable(importer.import_bundle)",
                    "assert _bundle_importer.__name__ == 'gpt_exporter.providers.gpt.importer._bundle_importer'",
                    "assert callable(markdown.export_canonical_markdown)",
                    "assert callable(gpt_markdown.export_markdown)",
                    "assert 'gpt_exporter.providers.gpt.export._native_markdown' not in sys.modules",
                    "assert docx._implementation().__name__ == 'gpt_exporter.export._legacy_docx'",
                    "assert callable(engine.update_index)",
                    "assert callable(indexing.update_index)",
                    "assert 'gpt_exporter.providers.gpt.indexing._native_indexer' not in sys.modules",
                    "assert collector_path().is_file()",
                    "assert 'chatgpt-archive-source.json' in collector_path().read_text(encoding='utf-8')",
                ]
            )

            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=temporary_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")

    def test_provider_collector_matches_source_collector(self) -> None:
        # Compare text rather than raw checkout bytes. Git may materialize LF or
        # CRLF differently depending on the local Windows configuration.
        source = (REPOSITORY_ROOT / "collect_chatgpt_archive.js").read_text(
            encoding="utf-8"
        )
        packaged = (
            REPOSITORY_ROOT
            / "gpt_exporter"
            / "providers"
            / "gpt"
            / "resources"
            / "collect_chatgpt_archive.js"
        ).read_text(encoding="utf-8")

        self.assertEqual(packaged, source)


if __name__ == "__main__":
    unittest.main()
