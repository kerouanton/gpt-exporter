import unittest
from pathlib import Path

import msne
from gpt_exporter.application import main as application_main


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

LEGACY_ROOT_LAUNCHERS = (
    "archive_browser.py",
    "archive_chats.py",
    "archive_core.py",
    "archive_gui_workflow.py",
    "audit_asset_references.py",
    "build_asset_manifest.py",
    "build_browser_asset_cache_seed.py",
    "check_environment.py",
    "export_all.py",
    "export_docx.py",
    "export_markdown.py",
    "gpt_exporter_gui.py",
    "import_browser_bundle.py",
    "index_chatgpt_archive.py",
    "inventory_media.py",
)


class MsneEntrypointTests(unittest.TestCase):
    def test_canonical_source_launcher_delegates_to_shared_application(self) -> None:
        self.assertIs(msne.main, application_main)

    def test_legacy_root_launchers_are_removed(self) -> None:
        for filename in LEGACY_ROOT_LAUNCHERS:
            with self.subTest(filename=filename):
                self.assertFalse((REPOSITORY_ROOT / filename).exists())

    def test_provider_specific_tools_live_outside_repository_root(self) -> None:
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "packages"
                / "export-provider-chatgpt"
                / "src"
                / "export_provider_chatgpt"
                / "indexing"
                / "cli.py"
            ).is_file()
        )
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "packages"
                / "export-provider-discord"
                / "src"
                / "export_provider_discord"
                / "collector.py"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
