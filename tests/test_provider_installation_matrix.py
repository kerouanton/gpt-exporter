from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


class ProviderInstallationMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.packages = {
            "gpt": (
                self.repo_root / "packages" / "export-provider-chatgpt" / "src",
                "export_provider_chatgpt.plugin",
            ),
            "discord": (
                self.repo_root / "packages" / "export-provider-discord" / "src",
                "export_provider_discord.plugin",
            ),
        }

    def _run_case(self, provider_ids: tuple[str, ...]) -> None:
        path_lines = []
        entry_lines = []
        module_assertions = []
        for provider_id in provider_ids:
            package_src, module_name = self.packages[provider_id]
            path_lines.append(f"sys.path.insert(0, {str(package_src)!r})")
            entry_lines.append(
                "entries.append(EntryPoint("
                f"{provider_id!r}, {module_name + ':create_provider'!r}, "
                f"importlib.import_module({module_name!r}).create_provider))"
            )
            module_assertions.append(
                f"assert result.registry.get({provider_id!r}).__class__.__module__ == {module_name!r}"
            )

        script = "\n".join(
            [
                "import importlib",
                "import sys",
                "from gpt_exporter.core.provider_discovery import PROVIDER_ENTRY_POINT_GROUP",
                "from gpt_exporter.provider_loader import discover_available_providers",
                *path_lines,
                "class EntryPoint:",
                "    def __init__(self, name, value, factory):",
                "        self.name = name",
                "        self.value = value",
                "        self.group = PROVIDER_ENTRY_POINT_GROUP",
                "        self._factory = factory",
                "    def load(self):",
                "        return self._factory",
                "entries = []",
                *entry_lines,
                "result = discover_available_providers(",
                "    include_embedded=False,",
                "    entry_points=lambda: entries,",
                ")",
                f"assert result.registry.provider_ids() == {provider_ids!r}",
                "assert result.failures == ()",
                *module_assertions,
            ]
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_host_with_zero_providers_is_valid(self) -> None:
        self._run_case(())

    def test_host_with_chatgpt_only_discovers_chatgpt_package(self) -> None:
        self._run_case(("gpt",))

    def test_host_with_discord_only_discovers_discord_package(self) -> None:
        self._run_case(("discord",))

    def test_host_with_both_provider_packages_discovers_both(self) -> None:
        self._run_case(("gpt", "discord"))


if __name__ == "__main__":
    unittest.main()
