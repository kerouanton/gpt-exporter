from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class GPTShellBoundaryTests(unittest.TestCase):
    def test_concrete_gpt_gui_lives_under_provider(self) -> None:
        provider_app = REPOSITORY_ROOT / "gpt_exporter" / "providers" / "gpt" / "ui" / "app.py"
        root_launcher = REPOSITORY_ROOT / "gpt_exporter_gui.py"
        self.assertTrue(provider_app.is_file())
        provider_text = provider_app.read_text(encoding="utf-8")
        launcher_text = root_launcher.read_text(encoding="utf-8")
        self.assertIn("Open ChatGPT", provider_text)
        self.assertIn("providers.gpt.ui", launcher_text)
        self.assertNotIn("Open ChatGPT", launcher_text)
        self.assertNotIn("chatgpt-archive-source.json", launcher_text)

    def test_root_compatibility_launchers_contain_no_gpt_schema_logic(self) -> None:
        launchers = (
            "archive_chats.py",
            "export_all.py",
            "inventory_media.py",
            "build_asset_manifest.py",
            "audit_asset_references.py",
            "build_browser_asset_cache_seed.py",
            "check_environment.py",
            "gpt_exporter_gui.py",
        )
        forbidden = (
            "chatgpt.com",
            "chatgpt-archive-source.json",
            "current_node",
            "asset_pointer",
            "gizmo_id",
            'data.get("mapping"',
            "conversation.mapping",
        )
        for name in launchers:
            text = (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, text, f"{name} still contains GPT implementation marker {marker!r}")

    def test_provider_cli_owns_active_gpt_commands(self) -> None:
        cli = REPOSITORY_ROOT / "gpt_exporter" / "providers" / "gpt" / "cli"
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


if __name__ == "__main__":
    unittest.main()
