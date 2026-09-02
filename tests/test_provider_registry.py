import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

from gpt_exporter.providers import BUILTIN_PROVIDERS, CHATGPT_PROVIDER, ProviderRegistry


class ProviderRegistryTests(unittest.TestCase):
    def test_builtin_registry_contains_chatgpt(self) -> None:
        self.assertIs(BUILTIN_PROVIDERS.get("chatgpt"), CHATGPT_PROVIDER)
        self.assertEqual(BUILTIN_PROVIDERS.all(), (CHATGPT_PROVIDER,))

    def test_registry_rejects_duplicate_provider_keys(self) -> None:
        registry = ProviderRegistry((CHATGPT_PROVIDER,))
        with self.assertRaises(ValueError):
            registry.register(CHATGPT_PROVIDER)

    def test_registry_lookup_is_case_insensitive(self) -> None:
        registry = ProviderRegistry((CHATGPT_PROVIDER,))
        self.assertIs(registry.get("ChatGPT"), CHATGPT_PROVIDER)


if __name__ == "__main__":
    unittest.main()
