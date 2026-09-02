import tempfile
import unittest
from pathlib import Path

from gpt_exporter.providers import CHATGPT_PROVIDER, ProviderRegistry
from gpt_exporter.workspaces import (
    Workspace,
    WorkspaceRegistry,
    load_startup_workspaces,
    load_workspace_registry,
    save_workspace_registry,
)


class WorkspacePersistenceTests(unittest.TestCase):
    def test_registry_round_trip_preserves_provider_and_archive_root(self) -> None:
        providers = ProviderRegistry((CHATGPT_PROVIDER,))
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            config = root / "workspaces.json"
            registry = WorkspaceRegistry(
                (
                    Workspace(
                        key="personal",
                        display_name="ChatGPT Personal",
                        provider=CHATGPT_PROVIDER,
                        archive_root=root / "ChatGPT Personal Archive",
                    ),
                    Workspace(
                        key="work",
                        display_name="ChatGPT Work",
                        provider=CHATGPT_PROVIDER,
                        archive_root=root / "ChatGPT Work Archive",
                    ),
                )
            )

            save_workspace_registry(registry, config)
            loaded = load_workspace_registry(
                config,
                providers=providers,
                fallback_to_defaults=False,
            )

            self.assertEqual([item.key for item in loaded.all()], ["personal", "work"])
            self.assertEqual(loaded.get("personal").provider.key, "chatgpt")
            self.assertEqual(
                loaded.get("work").database_path,
                (root / "ChatGPT Work Archive" / "conversations-index.sqlite").resolve(),
            )

    def test_startup_loader_uses_persisted_workspaces(self) -> None:
        providers = ProviderRegistry((CHATGPT_PROVIDER,))
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            config = root / "workspaces.json"
            registry = WorkspaceRegistry(
                (
                    Workspace(
                        key="alternate",
                        display_name="Alternate ChatGPT",
                        provider=CHATGPT_PROVIDER,
                        archive_root=root / "Alternate Archive",
                    ),
                )
            )
            save_workspace_registry(registry, config)

            loaded = load_startup_workspaces(providers=providers, path=config)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.get("alternate").display_name, "Alternate ChatGPT")
            self.assertEqual(
                loaded.get("alternate").archive_root,
                (root / "Alternate Archive").resolve(),
            )

    def test_startup_loader_falls_back_when_configuration_is_invalid(self) -> None:
        providers = ProviderRegistry((CHATGPT_PROVIDER,))
        with tempfile.TemporaryDirectory() as temp_name:
            config = Path(temp_name) / "workspaces.json"
            config.write_text("{not valid json", encoding="utf-8")

            loaded = load_startup_workspaces(providers=providers, path=config)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.get("chatgpt").provider.key, "chatgpt")

    def test_missing_configuration_can_fall_back_to_provider_defaults(self) -> None:
        providers = ProviderRegistry((CHATGPT_PROVIDER,))
        with tempfile.TemporaryDirectory() as temp_name:
            missing = Path(temp_name) / "missing.json"
            loaded = load_workspace_registry(missing, providers=providers)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded.get("chatgpt").provider.key, "chatgpt")

    def test_registry_replace_and_remove_do_not_touch_archive_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "archive"
            archive.mkdir()
            sentinel = archive / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")
            registry = WorkspaceRegistry(
                (
                    Workspace(
                        key="chatgpt",
                        display_name="ChatGPT",
                        provider=CHATGPT_PROVIDER,
                        archive_root=archive,
                    ),
                )
            )
            registry.replace(
                Workspace(
                    key="chatgpt",
                    display_name="Renamed",
                    provider=CHATGPT_PROVIDER,
                    archive_root=archive,
                )
            )
            removed = registry.remove("chatgpt")

            self.assertEqual(removed.display_name, "Renamed")
            self.assertTrue(sentinel.is_file())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
