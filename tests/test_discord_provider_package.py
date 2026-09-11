from __future__ import annotations

import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


class DiscordProviderPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.package_root = self.repo_root / "packages" / "export-provider-discord"
        self.package_src = self.package_root / "src"

    def test_package_declares_independent_distribution_and_entry_point(self) -> None:
        metadata = tomllib.loads((self.package_root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["name"], "export-provider-discord")
        self.assertIn("gpt-exporter>=2.9.0", metadata["project"]["dependencies"])
        self.assertEqual(
            metadata["project"]["entry-points"]["gpt_exporter.provider_plugins"]["discord"],
            "export_provider_discord.plugin:create_provider",
        )

    def test_host_distribution_no_longer_advertises_discord_entry_point(self) -> None:
        metadata = tomllib.loads((self.repo_root / "pyproject.toml").read_text(encoding="utf-8"))
        entry_points = metadata["project"].get("entry-points", {}).get("gpt_exporter.provider_plugins", {})
        self.assertNotIn("discord", entry_points)

    def test_extracted_package_imports_and_constructs_provider(self) -> None:
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(self.package_src)!r}); "
            "from export_provider_discord.plugin import create_provider; "
            "p=create_provider(); "
            "assert p.descriptor.provider_id == 'discord'; "
            "assert p.__class__.__module__.startswith('export_provider_discord')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=self.repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extracted_package_owns_collector_resources(self) -> None:
        resources = self.package_src / "export_provider_discord" / "resources"
        self.assertGreater((resources / "export_current_dm.js").stat().st_size, 1000)
        self.assertGreater((resources / "delete_own_messages.js").stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
