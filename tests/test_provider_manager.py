from __future__ import annotations

import unittest

from gpt_exporter.core import ProviderDescriptor, ProviderRegistry
from gpt_exporter.core.provider_discovery import (
    ProviderDiscoveryFailure,
    ProviderDiscoveryResult,
)
from gpt_exporter.provider_manager import ProviderManager, ProviderState


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
        manager = ProviderManager(ProviderDiscoveryResult(registry=registry))

        self.assertIs(manager.registry, registry)
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
        manager = ProviderManager(
            ProviderDiscoveryResult(registry=ProviderRegistry(), failures=failures)
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
        manager = ProviderManager(ProviderDiscoveryResult(registry=registry))
        self.assertEqual(
            tuple(record.provider_id for record in manager.records()),
            ("alpha", "zeta"),
        )


if __name__ == "__main__":
    unittest.main()
