from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from gpt_exporter.provider_artifacts import (
    ProviderArtifactStore,
    inspect_provider_wheel,
)


class ProviderArtifactTests(unittest.TestCase):
    def _write_wheel(
        self,
        path: Path,
        *,
        distribution: str = "export-provider-synthetic",
        version: str = "1.2.3",
        entry_points: str | None = None,
        extra_members: dict[str, bytes] | None = None,
    ) -> Path:
        dist_info = f"{distribution.replace('-', '_')}-{version}.dist-info"
        if entry_points is None:
            entry_points = (
                "[gpt_exporter.provider_plugins]\n"
                "synthetic = synthetic_provider.plugin:create_provider\n"
            )
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                f"{dist_info}/METADATA",
                f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n",
            )
            archive.writestr(f"{dist_info}/entry_points.txt", entry_points)
            archive.writestr("synthetic_provider/__init__.py", b"")
            archive.writestr(
                "synthetic_provider/plugin.py",
                b"def create_provider():\n    return None\n",
            )
            for name, data in (extra_members or {}).items():
                archive.writestr(name, data)
        return path

    def test_inspect_provider_wheel_reports_identity_entry_point_and_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel = self._write_wheel(Path(temporary) / "synthetic.whl")
            artifact = inspect_provider_wheel(wheel)

            self.assertEqual(artifact.distribution_name, "export-provider-synthetic")
            self.assertEqual(artifact.version, "1.2.3")
            self.assertEqual(
                artifact.entry_points,
                (("synthetic", "synthetic_provider.plugin:create_provider"),),
            )
            self.assertEqual(
                artifact.sha256,
                hashlib.sha256(wheel.read_bytes()).hexdigest(),
            )

    def test_install_extracts_to_isolated_distribution_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            wheel = self._write_wheel(base / "synthetic.whl")
            store = ProviderArtifactStore(base / "providers")

            artifact = store.install(wheel)
            destination = store.destination_for(artifact)

            self.assertTrue((destination / "synthetic_provider" / "plugin.py").is_file())
            self.assertEqual(store.installed_roots(), (destination,))

    def test_reinstall_replaces_previous_distribution_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            store = ProviderArtifactStore(base / "providers")
            first = self._write_wheel(
                base / "first.whl",
                version="1.0",
                extra_members={"synthetic_provider/old.py": b"old\n"},
            )
            second = self._write_wheel(base / "second.whl", version="2.0")

            store.install(first)
            artifact = store.install(second)
            destination = store.destination_for(artifact)

            self.assertFalse((destination / "synthetic_provider" / "old.py").exists())
            metadata_files = tuple(destination.glob("*.dist-info/METADATA"))
            self.assertEqual(len(metadata_files), 1)
            self.assertIn("Version: 2.0", metadata_files[0].read_text(encoding="utf-8"))
            self.assertFalse(destination.with_name(destination.name + ".previous").exists())

    def test_non_provider_wheel_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel = self._write_wheel(
                Path(temporary) / "ordinary.whl",
                entry_points="[console_scripts]\nordinary = ordinary:main\n",
            )
            with self.assertRaisesRegex(ValueError, "provider_plugins"):
                inspect_provider_wheel(wheel)

    def test_path_traversal_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            wheel = self._write_wheel(
                Path(temporary) / "unsafe.whl",
                extra_members={"../escape.py": b"bad\n"},
            )
            with self.assertRaisesRegex(ValueError, "Unsafe path"):
                inspect_provider_wheel(wheel)


if __name__ == "__main__":
    unittest.main()
