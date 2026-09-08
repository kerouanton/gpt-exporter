from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gpt_exporter.application import workspace_provider_arguments
from gpt_exporter.ui.workspace_selector import workspace_choices
from gpt_exporter.workspaces import ConversationWorkspace, WorkspaceCatalog


class WorkspaceTests(unittest.TestCase):
    def test_catalog_seeds_persists_and_restores_active_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "workspaces.json"
            catalog = WorkspaceCatalog(path)
            chatgpt = ConversationWorkspace("ChatGPT", "gpt", Path(temporary) / "gpt")
            discord = ConversationWorkspace("Discord", "discord", Path(temporary) / "discord")

            catalog.seed((chatgpt, discord))
            self.assertEqual(tuple(item.name for item in catalog.list()), ("ChatGPT", "Discord"))
            self.assertIsNone(catalog.get_active())

            selected = catalog.set_active("Discord")
            self.assertEqual(selected.provider_id, "discord")

            reopened = WorkspaceCatalog(path)
            self.assertEqual(reopened.get_active_name(), "Discord")
            self.assertEqual(reopened.get_active(), discord)

    def test_seed_does_not_replace_existing_workspace_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "workspaces.json"
            catalog = WorkspaceCatalog(path)
            original = ConversationWorkspace("ChatGPT", "gpt", Path(temporary) / "custom")
            catalog.seed((original,))
            catalog.seed((ConversationWorkspace("ChatGPT", "gpt", Path(temporary) / "default"),))
            self.assertEqual(catalog.get("ChatGPT").root_path, original.root_path)

    def test_disabled_workspace_cannot_become_active(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            catalog = WorkspaceCatalog(Path(temporary) / "workspaces.json")
            catalog.seed((ConversationWorkspace("Off", "synthetic", Path(temporary), enabled=False),))
            with self.assertRaisesRegex(ValueError, "disabled"):
                catalog.set_active("Off")

    def test_workspace_choices_hide_disabled_and_sort_by_name(self) -> None:
        workspaces = (
            ConversationWorkspace("Zulu", "z", Path("Z:/")),
            ConversationWorkspace("Alpha", "a", Path("A:/")),
            ConversationWorkspace("Hidden", "x", Path("X:/"), enabled=False),
        )
        self.assertEqual(tuple(item.name for item in workspace_choices(workspaces)), ("Alpha", "Zulu"))

    def test_provider_arguments_are_derived_from_workspace_root(self) -> None:
        root = Path("C:/archive")
        self.assertEqual(
            workspace_provider_arguments(ConversationWorkspace("GPT", "gpt", root)),
            ["--database", str(root / "conversations-index.sqlite")],
        )
        self.assertEqual(
            workspace_provider_arguments(ConversationWorkspace("Discord", "discord", root)),
            ["--archive-root", str(root)],
        )


if __name__ == "__main__":
    unittest.main()
