from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.core import ProviderDescriptor, ProviderRegistry
from gpt_exporter.core.provider_discovery import (
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
    ProviderDiscoverySuccess,
)
from gpt_exporter.provider_artifacts import ProviderArtifactStore
from gpt_exporter.provider_manager import ProviderManager, ProviderState
from gpt_exporter.provider_settings import ProviderSettings


class _Provider:
    def __init__(self, descriptor: ProviderDescriptor) -> None:
        self._descriptor = descriptor

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def discover(self, source):
        return ()

    def normalize(self, source):
        raise NotImplementedError


class ProviderManagerTests(unittest.TestCase):
    def _manager(
        self,
        discovery: ProviderDiscoveryResult,
        settings_path: Path,
    ) -> ProviderManager:
        return ProviderManager(
            discovery,
            settings=ProviderSettings(settings_path),
            artifact_store=ProviderArtifactStore(settings_path.parent / "managed-artifacts"),
        )

    @staticmethod
    def _write_managed_provider(
        root: Path,
        *,
        provider_id: str = "synthetic",
        distribution: str = "export-provider-synthetic",
        version: str = "1.2.3",
    ) -> None:
        destination = root / distribution
        dist_info = destination / f"{distribution.replace('-', '_')}-{version}.dist-info"
        dist_info.mkdir(parents=True)
        (dist_info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n",
            encoding="utf-8",
        )
        (dist_info / "entry_points.txt").write_text(
            "[gpt_exporter.provider_plugins]\n"
            f"{provider_id} = synthetic_provider.plugin:create_provider\n",
            encoding="utf-8",
        )
        (destination / ".msne-provider.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "distribution_name": distribution,
                    "version": version,
                    "sha256": "a" * 64,
                    "entry_points": [
                        [provider_id, "synthetic_provider.plugin:create_provider"]
                    ],
                    "source_filename": "synthetic.whl",
                    "installed_at": "2026-09-12T18:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

    def test_discovered_provider_is_exposed_as_enabled(self) -> None:
        registry = ProviderRegistry(
            [
                _Provider(
                    ProviderDescriptor(
                        provider_id="synthetic",
                        display_name="Synthetic",
                        version="3.4",
                        api_version=1,
                        capabilities=("archive", "workspace-actions"),
                    )
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            manager = self._manager(
                ProviderDiscoveryResult(registry=registry),
                Path(temporary) / "providers.json",
            )

        self.assertIs(manager.discovered_registry, registry)
        self.assertEqual(manager.registry.provider_ids(), ("synthetic",))
        self.assertEqual(len(manager.records()), 1)
        record = manager.records()[0]
        self.assertEqual(record.provider_id, "synthetic")
        self.assertEqual(record.display_name, "Synthetic")
        self.assertEqual(record.version, "3.4")
        self.assertEqual(record.api_version, 1)
        self.assertEqual(record.state, ProviderState.ENABLED)
        self.assertTrue(record.installed)
        self.assertTrue(record.discovered)
        self.assertFalse(record.managed)
        self.assertEqual(record.provenance_label, "Bundled / environment")
        self.assertEqual(record.capabilities, ("archive", "workspace-actions"))

    def test_managed_provenance_is_exposed_on_provider_record(self) -> None:
        registry = ProviderRegistry(
            [_Provider(ProviderDescriptor("synthetic", "Synthetic", "3.4"))]
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            settings_path = base / "providers.json"
            self._write_managed_provider(base / "managed-artifacts")
            manager = self._manager(
                ProviderDiscoveryResult(registry=registry),
                settings_path,
            )
            record = manager.records()[0]

            self.assertTrue(record.managed)
            self.assertEqual(record.provenance_label, "Managed")
            self.assertEqual(record.managed_distribution, "export-provider-synthetic")
            self.assertEqual(record.managed_version, "1.2.3")
            self.assertEqual(record.managed_sha256, "a" * 64)
            self.assertEqual(record.managed_source_filename, "synthetic.whl")
            self.assertEqual(
                manager.managed_info("synthetic").distribution_name,
                "export-provider-synthetic",
            )

    def test_managed_provenance_uses_descriptor_id_not_entry_point_alias(self) -> None:
        registry = ProviderRegistry(
            [_Provider(ProviderDescriptor("stable-id", "Synthetic", "3.4"))]
        )
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            settings_path = base / "providers.json"
            self._write_managed_provider(
                base / "managed-artifacts",
                provider_id="entry-point-alias",
            )
            discovery = ProviderDiscoveryResult(
                registry=registry,
                successes=(
                    ProviderDiscoverySuccess(
                        name="entry-point-alias",
                        value="synthetic_provider.plugin:create_provider",
                        provider_id="stable-id",
                    ),
                ),
            )
            manager = self._manager(discovery, settings_path)
            record = manager.records()[0]

            self.assertTrue(record.managed)
            self.assertEqual(record.provider_id, "stable-id")
            self.assertEqual(
                manager.managed_info("stable-id").distribution_name,
                "export-provider-synthetic",
            )

    def test_disable_is_durable_and_filters_active_registry(self) -> None:
        discovery = ProviderDiscoveryResult(
            registry=ProviderRegistry(
                [
                    _Provider(ProviderDescriptor("alpha", "Alpha", "1")),
                    _Provider(ProviderDescriptor("beta", "Beta", "1")),
                ]
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "providers.json"
            manager = self._manager(discovery, settings_path)
            manager.set_enabled("beta", False)
            reloaded = self._manager(discovery, settings_path)

            records = {record.provider_id: record for record in reloaded.records()}
            self.assertEqual(records["beta"].state, ProviderState.DISABLED)
            self.assertEqual(records["alpha"].state, ProviderState.ENABLED)
            self.assertEqual(reloaded.registry.provider_ids(), ("alpha",))
            self.assertEqual(
                ProviderSettings(settings_path).disabled_ids(),
                frozenset({"beta"}),
            )

            reloaded.set_enabled("beta", True)
            self.assertEqual(reloaded.registry.provider_ids(), ("alpha", "beta"))
            self.assertEqual(
                {record.provider_id: record.state for record in reloaded.records()},
                {"alpha": ProviderState.ENABLED, "beta": ProviderState.ENABLED},
            )

    def test_all_healthy_providers_can_be_disabled_and_reenabled_in_one_manager(self) -> None:
        discovery = ProviderDiscoveryResult(
            registry=ProviderRegistry(
                [
                    _Provider(ProviderDescriptor("alpha", "Alpha", "1")),
                    _Provider(ProviderDescriptor("beta", "Beta", "1")),
                ]
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "providers.json"
            manager = self._manager(discovery, settings_path)
            manager.set_enabled("alpha", False)
            self.assertEqual(manager.registry.provider_ids(), ("beta",))
            manager.set_enabled("beta", False)
            self.assertEqual(manager.registry.provider_ids(), ())
            self.assertTrue(
                all(record.state == ProviderState.DISABLED for record in manager.records())
            )

            manager.set_enabled("alpha", True)
            self.assertEqual(manager.registry.provider_ids(), ("alpha",))
            self.assertEqual(
                {record.provider_id: record.state for record in manager.records()},
                {"alpha": ProviderState.ENABLED, "beta": ProviderState.DISABLED},
            )

    def test_duplicate_failure_does_not_block_healthy_provider_toggle(self) -> None:
        discovery = ProviderDiscoveryResult(
            registry=ProviderRegistry(
                [_Provider(ProviderDescriptor("alpha", "Zulu Healthy", "1"))]
            ),
            failures=(
                ProviderDiscoveryFailure(
                    name="alpha-duplicate",
                    value="duplicate.plugin:create_provider",
                    error="ValueError: duplicate provider id: alpha",
                    provider_id="alpha",
                    display_name="Aardvark Broken Duplicate",
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "providers.json"
            manager = self._manager(discovery, settings_path)
            manager.set_enabled("alpha", False)

            healthy = next(record for record in manager.records() if record.discovered)
            broken = next(record for record in manager.records() if not record.discovered)
            self.assertEqual(healthy.state, ProviderState.DISABLED)
            self.assertEqual(broken.state, ProviderState.BROKEN)
            self.assertEqual(manager.registry.provider_ids(), ())

    def test_incompatible_failure_retains_provider_descriptor_metadata(self) -> None:
        failures = (
            ProviderDiscoveryFailure(
                name="entry-point-alias",
                value="future_provider.plugin:create_provider",
                error="ValueError: provider API version 2 is incompatible with core API version 1",
                provider_id="future-provider",
                display_name="Future Provider",
                version="9.7",
                api_version=2,
                capabilities=("archive", "future-capability"),
            ),
            ProviderDiscoveryFailure(
                name="broken-provider",
                value="broken_provider.plugin:create_provider",
                error="ImportError: synthetic failure",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            manager = self._manager(
                ProviderDiscoveryResult(registry=ProviderRegistry(), failures=failures),
                Path(temporary) / "providers.json",
            )
        records = {record.provider_id: record for record in manager.records()}

        future = records["future-provider"]
        self.assertEqual(future.state, ProviderState.INCOMPATIBLE)
        self.assertEqual(future.display_name, "Future Provider")
        self.assertEqual(future.version, "9.7")
        self.assertEqual(future.api_version, 2)
        self.assertEqual(future.capabilities, ("archive", "future-capability"))
        self.assertFalse(future.discovered)
        self.assertIn("API version 2", future.error)

        broken = records["broken-provider"]
        self.assertEqual(broken.state, ProviderState.BROKEN)
        self.assertEqual(broken.display_name, "broken-provider")
        self.assertIsNone(broken.api_version)

    def test_records_have_stable_display_order(self) -> None:
        registry = ProviderRegistry(
            [
                _Provider(ProviderDescriptor("zeta", "Zeta", "1")),
                _Provider(ProviderDescriptor("alpha", "Alpha", "1")),
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            manager = self._manager(
                ProviderDiscoveryResult(registry=registry),
                Path(temporary) / "providers.json",
            )
        self.assertEqual(
            tuple(record.provider_id for record in manager.records()),
            ("alpha", "zeta"),
        )


if __name__ == "__main__":
    unittest.main()
