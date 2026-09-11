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
    def test_core_package_loads_without_repository_root_modules_or_providers(self) -> None:
        """Exercise the provider-neutral host from package-only imports."""

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_package = REPOSITORY_ROOT / "gpt_exporter"
            target_package = temporary_root / "gpt_exporter"

            import shutil

            shutil.copytree(source_package, target_package)
            shutil.rmtree(target_package / "providers", ignore_errors=True)
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
                    "assert importlib.util.find_spec('export_provider_chatgpt') is None",
                    "assert importlib.util.find_spec('export_provider_discord') is None",
                    "import gpt_exporter.application",
                    "import gpt_exporter.pipeline",
                    "from gpt_exporter.archive import importer",
                    "from gpt_exporter.export import markdown, docx",
                    "from gpt_exporter.index import engine",
                    "from gpt_exporter.provider_loader import discover_available_providers",
                    "assert callable(importer.import_bundle)",
                    "assert callable(markdown.export_canonical_markdown)",
                    "assert docx._implementation().__name__ == 'gpt_exporter.export._markdown_docx_v28'",
                    "assert callable(engine.update_index)",
                    "result = discover_available_providers(include_embedded=False, entry_points=lambda: [])",
                    "assert result.registry.provider_ids() == ()",
                    "assert result.failures == ()",
                    "assert not any(name.startswith('gpt_exporter.providers.') for name in sys.modules)",
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

    def test_chatgpt_collector_exists_only_under_extracted_provider(self) -> None:
        provider_collector = (
            REPOSITORY_ROOT
            / "packages"
            / "export-provider-chatgpt"
            / "src"
            / "export_provider_chatgpt"
            / "resources"
            / "collect_chatgpt_archive.js"
        )
        self.assertTrue(provider_collector.is_file())
        self.assertFalse((REPOSITORY_ROOT / "collect_chatgpt_archive.js").exists())
        self.assertFalse(
            (
                REPOSITORY_ROOT
                / "gpt_exporter"
                / "resources"
                / "collect_chatgpt_archive.js"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
