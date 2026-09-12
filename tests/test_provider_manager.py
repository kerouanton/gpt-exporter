from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gpt_exporter.core import ProviderDescriptor, ProviderRegistry
from gpt_exporter.core.provider_discovery import (
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
)
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
        return ProviderManager(discovery, settings=ProviderSettings(settings_path))

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
        self.assertEqual(record.capabilities, ("archive", "workspace-actions"))

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
            enabled_again = self._manager(discovery, settings_path)
            self.assertEqual(
                enabled_again.registry.provider_ids(),
                ("alpha", "beta"),
            )

    def test_last_healthy_provider_cannot_be_disabled(self) -> None:
        discovery = ProviderDiscoveryResult(
            registry=ProviderRegistry(
                [_Provider(ProviderDescriptor("only", "Only", "1"))]
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            manager = self._manager(
                discovery,
                Path(temporary) / "providers.json",
            )
            with self.assertRaisesRegex(ValueError, "At least one healthy provider"):
                manager.set_enabled("only", False)

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
