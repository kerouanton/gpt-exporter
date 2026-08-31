import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

from gpt_exporter.providers import CHATGPT_PROVIDER, ExporterProvider


class ProviderContractTests(unittest.TestCase):
    def test_chatgpt_provider_declares_source_specific_identity(self) -> None:
        provider = CHATGPT_PROVIDER

        self.assertIsInstance(provider, ExporterProvider)
        self.assertEqual(provider.key, "chatgpt")
        self.assertEqual(provider.display_name, "ChatGPT")
        self.assertEqual(provider.archive_directory_name, "ChatGPT Archive")
        self.assertEqual(provider.website_url, "https://chatgpt.com/")
        self.assertEqual(provider.source_bundle_name, "chatgpt-archive-source.json")
        self.assertEqual(provider.collector_name, "collect_chatgpt_archive.js")

    def test_chatgpt_provider_collector_is_packaged_and_non_empty(self) -> None:
        provider = CHATGPT_PROVIDER

        self.assertTrue(provider.collector_path.is_file())
        self.assertTrue(provider.read_collector_source().strip())

    def test_provider_contract_contains_no_gui_responsibility(self) -> None:
        fields = set(ExporterProvider.__dataclass_fields__)

        self.assertNotIn("window", fields)
        self.assertNotIn("menu", fields)
        self.assertNotIn("search", fields)
        self.assertNotIn("keyword_cloud", fields)
        self.assertNotIn("docx_renderer", fields)


if __name__ == "__main__":
    unittest.main()
