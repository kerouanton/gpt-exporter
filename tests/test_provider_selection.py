from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.application import build_provider_registry, main as application_main
from gpt_exporter.core import ProviderDescriptor, ProviderRegistry
from gpt_exporter.ui.provider_selector import provider_choices


class _SyntheticProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor("synthetic", "Synthetic", "1")

    def discover(self, source):
        return ()

    def normalize(self, source):
        raise NotImplementedError


class ProviderSelectionTests(unittest.TestCase):
    def test_registry_accepts_provider_without_concrete_dependency(self) -> None:
        registry = ProviderRegistry([_SyntheticProvider()])
        self.assertEqual(registry.provider_ids(), ("synthetic",))
        self.assertEqual(registry.get("synthetic").descriptor.display_name, "Synthetic")

    def test_registry_rejects_duplicate_provider_id(self) -> None:
        registry = ProviderRegistry([_SyntheticProvider()])
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(_SyntheticProvider())

    def test_provider_choices_are_sorted_for_ui(self) -> None:
        descriptors = (
            ProviderDescriptor("z", "Zulu", "1"),
            ProviderDescriptor("a", "Alpha", "1"),
        )
        self.assertEqual(
            tuple(item.provider_id for item in provider_choices(descriptors)),
            ("a", "z"),
        )

    def test_installed_registry_contains_chatgpt_and_discord(self) -> None:
        self.assertEqual(build_provider_registry().provider_ids(), ("discord", "gpt"))

    def test_direct_provider_selection_skips_dialog_and_launches_registered_ui(self) -> None:
        registry = ProviderRegistry([_SyntheticProvider()])
        launcher = mock.Mock(return_value=23)
        with (
            mock.patch("gpt_exporter.application.build_provider_registry", return_value=registry),
            mock.patch("gpt_exporter.application.build_provider_launchers", return_value={"synthetic": launcher}),
            mock.patch("gpt_exporter.application.choose_provider") as chooser,
        ):
            result = application_main(["--provider", "synthetic", "--provider-specific"])
        self.assertEqual(result, 23)
        chooser.assert_not_called()
        launcher.assert_called_once_with(["--provider-specific"])

    def test_interactive_selection_uses_registry_descriptor(self) -> None:
        registry = ProviderRegistry([_SyntheticProvider()])
        launcher = mock.Mock(return_value=0)
        with (
            mock.patch("gpt_exporter.application.build_provider_registry", return_value=registry),
            mock.patch("gpt_exporter.application.build_provider_launchers", return_value={"synthetic": launcher}),
            mock.patch("gpt_exporter.application.choose_provider", return_value="synthetic") as chooser,
        ):
            result = application_main([])
        self.assertEqual(result, 0)
        descriptors = chooser.call_args.args[0]
        self.assertEqual(tuple(item.provider_id for item in descriptors), ("synthetic",))
        launcher.assert_called_once_with([])

    def test_importing_application_does_not_eagerly_load_concrete_providers(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; import gpt_exporter.application; "
            "raise SystemExit(int(any(name.startswith(('gpt_exporter.providers.gpt', "
            "'gpt_exporter.providers.discord')) for name in sys.modules)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=repo_root,
            check=False,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
