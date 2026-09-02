import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.providers.base import ExporterProvider
from gpt_exporter.providers.registry import ProviderRegistry
from gpt_exporter.workspaces import Workspace, WorkspaceRegistry, build_default_workspaces


class WorkspaceTests(unittest.TestCase):
    def _provider(self, key: str, name: str, archive_name: str) -> ExporterProvider:
        return ExporterProvider(
            key=key,
            display_name=name,
            archive_directory_name=archive_name,
            website_url=f"https://{key}.example.invalid/",
            source_bundle_name=f"{key}-archive-source.json",
            collector_path=Path(__file__),
            importer=mock.Mock(),
            normalizer=mock.Mock(),
        )

    def test_workspace_binds_provider_and_archive_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            provider = self._provider("chatgpt", "ChatGPT", "ChatGPT Archive")
            workspace = Workspace(
                key="personal",
                display_name="ChatGPT Personal",
                provider=provider,
                archive_root=Path(temp_name) / "ChatGPT Archive",
            )

            self.assertIs(workspace.provider, provider)
            self.assertEqual(workspace.paths.root, workspace.archive_root)
            self.assertEqual(workspace.database_path, workspace.archive_root / "conversations-index.sqlite")

    def test_default_workspaces_use_each_provider_archive_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            chatgpt = self._provider("chatgpt", "ChatGPT", "ChatGPT Archive")
            discord = self._provider("discord", "Discord", "Discord Archive")
            registry = ProviderRegistry((chatgpt, discord))

            workspaces = build_default_workspaces(registry, documents_root=temp_name)

            self.assertEqual(
                workspaces.get("chatgpt").archive_root,
                Path(temp_name).resolve() / "ChatGPT Archive",
            )
            self.assertEqual(
                workspaces.get("discord").archive_root,
                Path(temp_name).resolve() / "Discord Archive",
            )

    def test_registry_allows_multiple_workspaces_for_one_provider(self) -> None:
        provider = self._provider("chatgpt", "ChatGPT", "ChatGPT Archive")
        registry = WorkspaceRegistry(
            (
                Workspace("personal", "Personal", provider, Path("personal")),
                Workspace("work", "Work", provider, Path("work")),
            )
        )
        self.assertEqual(len(registry), 2)
        self.assertIs(registry.get("personal").provider, registry.get("work").provider)


if __name__ == "__main__":
    unittest.main()
