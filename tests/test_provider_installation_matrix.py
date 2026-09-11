from __future__ import annotations

import importlib
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

from gpt_exporter.core.provider_discovery import PROVIDER_ENTRY_POINT_GROUP
from gpt_exporter.provider_loader import discover_available_providers


class _EntryPoint:
    def __init__(self, name: str, value: str, factory):
        self.name = name
        self.value = value
        self.group = PROVIDER_ENTRY_POINT_GROUP
        self._factory = factory

    def load(self):
        return self._factory


class ProviderInstallationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.chatgpt_src = self.repo_root / "packages" / "export-provider-chatgpt" / "src"
        self.discord_src = self.repo_root / "packages" / "export-provider-discord" / "src"

    @contextmanager
    def _package_paths(self):
        original = list(sys.path)
        sys.path[:0] = [str(self.chatgpt_src), str(self.discord_src)]
        try:
            yield
        finally:
            sys.path[:] = original

    def _factory(self, module_name: str):
        with self._package_paths():
            module = importlib.import_module(module_name)
            return module.create_provider

    def _discover(self, *entries: _EntryPoint):
        return discover_available_providers(
            include_embedded=False,
            entry_points=lambda: list(entries),
        )

    def test_host_with_zero_providers_is_valid(self) -> None:
        result = self._discover()
        self.assertEqual(result.registry.provider_ids(), ())
        self.assertEqual(result.failures, ())

    def test_host_with_chatgpt_only_discovers_chatgpt_package(self) -> None:
        result = self._discover(
            _EntryPoint(
                "gpt",
                "export_provider_chatgpt.plugin:create_provider",
                self._factory("export_provider_chatgpt.plugin"),
            )
        )
        self.assertEqual(result.registry.provider_ids(), ("gpt",))
        self.assertEqual(result.registry.get("gpt").__class__.__module__, "export_provider_chatgpt.plugin")

    def test_host_with_discord_only_discovers_discord_package(self) -> None:
        result = self._discover(
            _EntryPoint(
                "discord",
                "export_provider_discord.plugin:create_provider",
                self._factory("export_provider_discord.plugin"),
            )
        )
        self.assertEqual(result.registry.provider_ids(), ("discord",))
        self.assertEqual(
            result.registry.get("discord").__class__.__module__,
            "export_provider_discord.plugin",
        )

    def test_host_with_both_provider_packages_discovers_both(self) -> None:
        result = self._discover(
            _EntryPoint(
                "gpt",
                "export_provider_chatgpt.plugin:create_provider",
                self._factory("export_provider_chatgpt.plugin"),
            ),
            _EntryPoint(
                "discord",
                "export_provider_discord.plugin:create_provider",
                self._factory("export_provider_discord.plugin"),
            ),
        )
        self.assertEqual(result.registry.provider_ids(), ("gpt", "discord"))
        self.assertEqual(result.failures, ())


if __name__ == "__main__":
    unittest.main()
