from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.provider_artifacts import ProviderArtifactStore, inspect_provider_wheel
from gpt_exporter.provider_runtime import (
    install_provider_with_validation,
    validate_provider_dependency_policy,
)


class ProviderRuntimeTests(unittest.TestCase):
    def _write_wheel(
        self,
        path: Path,
        *,
        version: str = "1.0",
        dependency: str = "gpt-exporter>=2.9.0",
        provider_id: str = "synthetic",
        api_version: int = 1,
        broken: bool = False,
    ) -> Path:
        distribution = "export-provider-synthetic"
        dist_info = f"export_provider_synthetic-{version}.dist-info"
        metadata = (
            "Metadata-Version: 2.1\n"
            f"Name: {distribution}\n"
            f"Version: {version}\n"
        )
        if dependency:
            metadata += f"Requires-Dist: {dependency}\n"
        plugin = (
            "from pathlib import Path\n"
            "from gpt_exporter.core import ProviderDescriptor\n"
            "class Provider:\n"
            "    @property\n"
            "    def descriptor(self):\n"
            f"        return ProviderDescriptor({provider_id!r}, 'Synthetic', {version!r}, api_version={api_version})\n"
            "    def discover(self, source: Path):\n"
            "        return ()\n"
            "    def normalize(self, source: Path):\n"
            "        raise NotImplementedError\n"
            "def create_provider():\n"
            + ("    raise RuntimeError('boom')\n" if broken else "    return Provider()\n")
        )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"{dist_info}/METADATA", metadata)
            archive.writestr(
                f"{dist_info}/entry_points.txt",
                "[gpt_exporter.provider_plugins]\n"
                "entry-point-alias = synthetic_provider.plugin:create_provider\n",
            )
            archive.writestr("synthetic_provider/__init__.py", "")
            archive.writestr("synthetic_provider/plugin.py", plugin)
        return path

    def test_dependency_policy_allows_host_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel = self._write_wheel(Path(temporary) / "provider.whl")
            requirements = validate_provider_dependency_policy(wheel)
        self.assertEqual(requirements, ("gpt-exporter>=2.9.0",))

    def test_dependency_policy_rejects_third_party_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel = self._write_wheel(
                Path(temporary) / "provider.whl",
                dependency="requests>=2",
            )
            with self.assertRaisesRegex(ValueError, "unsupported runtime dependencies"):
                validate_provider_dependency_policy(wheel)

    def test_validated_install_accepts_provider_id_different_from_entry_point_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            wheel = self._write_wheel(base / "provider.whl", provider_id="actual-provider")
            store = ProviderArtifactStore(base / "providers")
            artifact = inspect_provider_wheel(wheel)

            installed, provider_ids = install_provider_with_validation(store, artifact)

            self.assertEqual(installed.version, "1.0")
            self.assertEqual(provider_ids, ("actual-provider",))
            self.assertTrue(store.destination_for(artifact).is_dir())

    def test_failed_update_restores_previous_managed_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            store = ProviderArtifactStore(base / "providers")
            good = inspect_provider_wheel(self._write_wheel(base / "good.whl", version="1.0"))
            install_provider_with_validation(store, good)
            broken = inspect_provider_wheel(
                self._write_wheel(base / "broken.whl", version="2.0", broken=True)
            )

            with self.assertRaisesRegex(ValueError, "previous managed version was restored"):
                install_provider_with_validation(store, broken)

            managed = store.managed_for_distribution("export-provider-synthetic")
            self.assertIsNotNone(managed)
            assert managed is not None
            self.assertEqual(managed.version, "1.0")

    def test_failed_first_install_leaves_no_managed_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            store = ProviderArtifactStore(base / "providers")
            broken = inspect_provider_wheel(
                self._write_wheel(base / "broken.whl", broken=True)
            )

            with self.assertRaisesRegex(ValueError, "runtime validation failed"):
                install_provider_with_validation(store, broken)

            self.assertIsNone(store.managed_for_distribution("export-provider-synthetic"))


if __name__ == "__main__":
    unittest.main()
