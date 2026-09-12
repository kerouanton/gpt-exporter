from __future__ import annotations

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


class GPTShellBoundaryTests(unittest.TestCase):
    def test_concrete_gpt_gui_lives_under_provider(self) -> None:
        provider_app = CHATGPT_PROVIDER_ROOT / "ui" / "app.py"
        root_launcher = REPOSITORY_ROOT / "msne.py"
        self.assertTrue(provider_app.is_file())
        provider_text = provider_app.read_text(encoding="utf-8")
        launcher_text = root_launcher.read_text(encoding="utf-8")
        self.assertIn("Open ChatGPT", provider_text)
        self.assertIn("gpt_exporter.application", launcher_text)
        self.assertNotIn("Open ChatGPT", launcher_text)
        self.assertNotIn("chatgpt-archive-source.json", launcher_text)
        self.assertNotIn("export_provider_chatgpt", launcher_text)

    def test_historical_root_compatibility_launchers_are_removed(self) -> None:
        launchers = (
            "archive_chats.py",
            "archive_browser.py",
            "archive_core.py",
            "export_all.py",
            "inventory_media.py",
            "build_asset_manifest.py",
            "audit_asset_references.py",
            "build_browser_asset_cache_seed.py",
            "check_environment.py",
            "gpt_exporter_gui.py",
        )
        for name in launchers:
            self.assertFalse((REPOSITORY_ROOT / name).exists(), name)

    def test_provider_cli_owns_active_gpt_commands(self) -> None:
        cli = CHATGPT_PROVIDER_ROOT / "cli"
        expected = (
            "archive_chats.py",
            "export_all.py",
            "inventory_media.py",
            "build_asset_manifest.py",
            "audit_asset_references.py",
            "build_browser_asset_cache_seed.py",
            "check_environment.py",
        )
        for name in expected:
            self.assertTrue((cli / name).is_file(), name)

    def test_historical_browser_implementation_is_shared(self) -> None:
        shared = REPOSITORY_ROOT / "gpt_exporter" / "ui" / "browser"
        provider = CHATGPT_PROVIDER_ROOT / "ui" / "browser"
        shared_browser = shared / "archive_browser.py"
        shared_core = shared / "archive_core.py"
        provider_browser = provider / "archive_browser.py"
        provider_core = provider / "archive_core.py"

        self.assertGreater(shared_browser.stat().st_size, 50_000)
        self.assertGreater(shared_core.stat().st_size, 30_000)
        self.assertLess(provider_browser.stat().st_size, 1024)
        self.assertLess(provider_core.stat().st_size, 1024)
        self.assertIn("gpt_exporter.ui.browser", provider_browser.read_text(encoding="utf-8"))
        self.assertIn("gpt_exporter.ui.browser", provider_core.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
