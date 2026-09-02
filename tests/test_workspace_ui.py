import unittest
from pathlib import Path
from unittest import mock

import gpt_exporter_gui as gui
from gpt_exporter.providers.base import ExporterProvider
from gpt_exporter.workspaces import Workspace


class WorkspaceUiTests(unittest.TestCase):
    def test_archive_menu_uses_current_workspace_provider_name(self) -> None:
        provider = ExporterProvider(
            key="discord",
            display_name="Discord",
            archive_directory_name="Discord Archive",
            website_url="https://discord.example.invalid/",
            source_bundle_name="discord-archive-source.json",
            collector_path=Path(__file__),
            importer=mock.Mock(),
            normalizer=mock.Mock(),
        )
        workspace = Workspace(
            key="discord",
            display_name="Discord",
            provider=provider,
            archive_root=Path("Discord Archive"),
        )

        class FakeMenu:
            def __init__(self, master=None, **_kwargs):
                self.master = master
                self.entries = []

            def add_command(self, **kwargs):
                self.entries.append(("command", kwargs))

            def add_separator(self):
                self.entries.append(("separator", {}))

            def add_cascade(self, **kwargs):
                self.entries.append(("cascade", kwargs))

        class FakeApp:
            def __init__(self):
                self.current_workspace = workspace
                self.menu = None

            def config(self, **kwargs):
                self.menu = kwargs.get("menu")

            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        app = FakeApp()
        with mock.patch.object(gui.tk, "Menu", FakeMenu):
            gui.GPTExporterApp._build_menu(app)

        archive_entry = next(
            details
            for kind, details in app.menu.entries
            if kind == "cascade" and details.get("label") == "Archive"
        )
        archive_labels = [
            details.get("label")
            for kind, details in archive_entry["menu"].entries
            if kind == "command"
        ]
        self.assertIn("Open Discord", archive_labels)
        self.assertNotIn("Open ChatGPT", archive_labels)


if __name__ == "__main__":
    unittest.main()
