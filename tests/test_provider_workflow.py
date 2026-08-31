import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.providers import CHATGPT_PROVIDER
from gpt_exporter.providers.base import ExporterProvider
from gpt_exporter.workflow import ProviderWorkflow


class ProviderWorkflowTests(unittest.TestCase):
    def test_chatgpt_workflow_uses_provider_acquisition_metadata(self) -> None:
        workflow = ProviderWorkflow(CHATGPT_PROVIDER)
        with tempfile.TemporaryDirectory() as temp_name:
            downloads = Path(temp_name)
            source = downloads / CHATGPT_PROVIDER.source_bundle_name
            source.write_text("{}", encoding="utf-8")

            found = workflow.find_source_bundle(download_directories=[downloads])

        self.assertEqual(found, source)
        self.assertEqual(workflow.read_collector_source(), CHATGPT_PROVIDER.read_collector_source())

    def test_run_archive_delegates_chatgpt_to_compatibility_pipeline(self) -> None:
        workflow = ProviderWorkflow(CHATGPT_PROVIDER)
        source = Path("C:/synthetic/chatgpt-archive-source.json")

        with mock.patch("gpt_exporter.workflow.archive_bundle", return_value=mock.sentinel.result) as archive:
            result = workflow.run_archive(
                archive_root=Path("C:/synthetic/archive"),
                source_bundle=source,
                delete_source=False,
            )

        archive.assert_called_once()
        _, kwargs = archive.call_args
        self.assertEqual(kwargs["source_bundle"], source)
        self.assertFalse(kwargs["delete_source"])
        self.assertIs(result, mock.sentinel.result)

    def test_unconnected_provider_is_rejected_explicitly(self) -> None:
        synthetic = ExporterProvider(
            key="synthetic",
            display_name="Synthetic",
            archive_directory_name="Synthetic Archive",
            website_url="https://example.invalid/",
            source_bundle_name="synthetic.json",
            collector_path=Path(__file__),
            importer=mock.Mock(),
            normalizer=mock.Mock(),
        )

        with self.assertRaises(NotImplementedError):
            ProviderWorkflow(synthetic).run_archive(convert_only=True)


if __name__ == "__main__":
    unittest.main()
