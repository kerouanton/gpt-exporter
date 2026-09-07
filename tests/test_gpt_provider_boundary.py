from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class GPTProviderBoundaryTests(unittest.TestCase):
    def test_provider_owns_chatgpt_archive_implementations(self) -> None:
        provider = REPOSITORY_ROOT / "gpt_exporter" / "providers" / "gpt"
        expected = (
            provider / "pipeline.py",
            provider / "importer" / "_bundle_importer.py",
            provider / "importer" / "__init__.py",
            provider / "ui" / "archive_workflow.py",
            provider / "ui" / "_archive_workflow.py",
            provider / "resources" / "collect_chatgpt_archive.js",
        )
        for path in expected:
            self.assertTrue(path.is_file(), f"ChatGPT implementation must live in provider: {path}")

    def test_old_bundle_importer_implementation_is_gone(self) -> None:
        self.assertFalse(
            (REPOSITORY_ROOT / "gpt_exporter" / "archive" / "_legacy_importer.py").exists()
        )

    def test_provider_modules_are_importable(self) -> None:
        from gpt_exporter.providers.gpt import pipeline
        from gpt_exporter.providers.gpt.importer import import_bundle
        from gpt_exporter.providers.gpt.resources import collector_path
        from gpt_exporter.providers.gpt.ui import archive_workflow

        self.assertTrue(callable(pipeline.archive_bundle))
        self.assertTrue(callable(import_bundle))
        self.assertTrue(collector_path().name == "collect_chatgpt_archive.js")
        self.assertTrue(callable(archive_workflow.open_chatgpt))

    def test_relocated_gui_preserves_historical_application_root(self) -> None:
        from gpt_exporter.providers.gpt.ui import archive_workflow

        self.assertEqual(archive_workflow.ROOT, REPOSITORY_ROOT)
        self.assertEqual(archive_workflow._implementation.ROOT, REPOSITORY_ROOT)
        self.assertEqual(
            archive_workflow.COLLECTOR_PATH,
            REPOSITORY_ROOT
            / "gpt_exporter"
            / "providers"
            / "gpt"
            / "resources"
            / "collect_chatgpt_archive.js",
        )


if __name__ == "__main__":
    unittest.main()
