from __future__ import annotations

import unittest
from dataclasses import dataclass
from pathlib import Path

from gpt_exporter.provider_sdk import (
    PROVIDER_API_VERSION,
    PROVIDER_ENTRY_POINT_GROUP,
    CanonicalConversation,
    ProviderDescriptor,
    discover_providers,
)


class SyntheticProvider:
    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="synthetic",
            display_name="Synthetic",
            version="1.0",
            api_version=PROVIDER_API_VERSION,
            capabilities=("normalize",),
        )

    def discover(self, source: Path):
        return ()

    def normalize(self, source: Path) -> CanonicalConversation:
        return CanonicalConversation(
            conversation_id="synthetic:1",
            provider_id="synthetic",
            title="Synthetic conversation",
            messages=(),
        )


@dataclass(frozen=True)
class FakeEntryPoint:
    name: str
    value: str
    group: str
    target: object

    def load(self):
        return self.target


class FakeEntryPoints(tuple):
    def select(self, *, group: str):
        return tuple(item for item in self if item.group == group)


class ProviderDiscoveryTests(unittest.TestCase):
    def test_zero_provider_discovery_is_valid(self) -> None:
        result = discover_providers(entry_points=lambda: FakeEntryPoints())
        self.assertEqual(result.registry.provider_ids(), ())
        self.assertEqual(result.failures, ())

    def test_unknown_synthetic_provider_is_discovered_without_core_changes(self) -> None:
        entry = FakeEntryPoint(
            name="synthetic",
            value="external.synthetic:provider",
            group=PROVIDER_ENTRY_POINT_GROUP,
            target=SyntheticProvider,
        )
        result = discover_providers(entry_points=lambda: FakeEntryPoints((entry,)))
        self.assertEqual(result.registry.provider_ids(), ("synthetic",))
        self.assertEqual(result.failures, ())
        self.assertEqual(result.registry.get("synthetic").descriptor.display_name, "Synthetic")

    def test_broken_provider_does_not_prevent_other_providers_loading(self) -> None:
        class BrokenEntryPoint(FakeEntryPoint):
            def load(self):
                raise RuntimeError("boom")

        broken = BrokenEntryPoint(
            name="broken",
            value="external.broken:provider",
            group=PROVIDER_ENTRY_POINT_GROUP,
            target=None,
        )
        working = FakeEntryPoint(
            name="synthetic",
            value="external.synthetic:provider",
            group=PROVIDER_ENTRY_POINT_GROUP,
            target=SyntheticProvider(),
        )
        result = discover_providers(entry_points=lambda: FakeEntryPoints((broken, working)))
        self.assertEqual(result.registry.provider_ids(), ("synthetic",))
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].name, "broken")
        self.assertIn("RuntimeError: boom", result.failures[0].error)

    def test_incompatible_api_version_is_rejected_nonfatally(self) -> None:
        class FutureProvider(SyntheticProvider):
            @property
            def descriptor(self) -> ProviderDescriptor:
                return ProviderDescriptor(
                    provider_id="future",
                    display_name="Future",
                    version="1.0",
                    api_version=PROVIDER_API_VERSION + 1,
                )

        entry = FakeEntryPoint(
            name="future",
            value="external.future:provider",
            group=PROVIDER_ENTRY_POINT_GROUP,
            target=FutureProvider,
        )
        result = discover_providers(entry_points=lambda: FakeEntryPoints((entry,)))
        self.assertEqual(result.registry.provider_ids(), ())
        self.assertEqual(len(result.failures), 1)
        self.assertIn("incompatible", result.failures[0].error)


if __name__ == "__main__":
    unittest.main()
