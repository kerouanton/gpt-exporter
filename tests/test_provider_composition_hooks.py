from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest import mock

import gpt_exporter.application as application
from gpt_exporter.core import ProviderDescriptor, ProviderRegistry
from gpt_exporter.workspaces import ConversationWorkspace


class SyntheticApplicationProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            "synthetic",
            "Synthetic",
            "1",
            capabilities=(
                "default-workspace",
                "legacy-ui",
                "workspace-actions",
                "workspace-arguments",
            ),
        )

    def discover(self, source):
        return ()

    def normalize(self, source):
        raise NotImplementedError

    def default_workspaces(self):
        return (
            ConversationWorkspace(
                "Synthetic Main",
                "synthetic",
                Path("C:/synthetic"),
            ),
        )

    def legacy_main(self):
        return lambda: 31

    def workspace_arguments(self, workspace):
        return ["--root", str(workspace.root_path)]

    def build_workspace_actions(self, app, workspace):
        return (app, workspace)


class ProviderCompositionHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = SyntheticApplicationProvider()
        self.registry = ProviderRegistry([self.provider])
        self.workspace = self.provider.default_workspaces()[0]

    def test_application_source_does_not_name_concrete_provider_packages(self) -> None:
        source = inspect.getsource(application)
        self.assertNotIn("export_provider_chatgpt", source)
        self.assertNotIn("export_provider_discord", source)

    def test_default_workspaces_are_supplied_by_provider_hook(self) -> None:
        self.assertEqual(application.build_default_workspaces(self.registry), (self.workspace,))

    def test_workspace_arguments_are_supplied_by_provider_hook(self) -> None:
        self.assertEqual(
            application.workspace_provider_arguments(self.workspace, registry=self.registry),
            ["--root", str(self.workspace.root_path)],
        )

    def test_workspace_actions_are_supplied_by_provider_hook(self) -> None:
        owner = object()
        self.assertEqual(
            application.build_workspace_actions(owner, self.workspace, registry=self.registry),
            (owner, self.workspace),
        )

    def test_legacy_launcher_is_supplied_by_provider_hook(self) -> None:
        launchers = application.build_provider_launchers(self.registry)
        with mock.patch.object(application.sys, "argv", ["app"]):
            self.assertEqual(launchers["synthetic"](["--flag"]), 31)


if __name__ == "__main__":
    unittest.main()
