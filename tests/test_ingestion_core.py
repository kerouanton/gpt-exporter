import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.ingestion import ingest_source_bundle, resolve_provider_archive_paths
from gpt_exporter.providers.base import ExporterProvider


class IngestionCoreTests(unittest.TestCase):
    def _provider(self, importer) -> ExporterProvider:
        collector = Path(__file__)
        return ExporterProvider(
            key="synthetic",
            display_name="Synthetic",
            archive_directory_name="Synthetic Archive",
            website_url="https://example.invalid/",
            source_bundle_name="synthetic.json",
            collector_path=collector,
            importer=importer,
        )

    def test_resolve_provider_archive_paths_uses_provider_default_directory(self) -> None:
        provider = self._provider(mock.Mock())

        with mock.patch("gpt_exporter.ingestion.default_archive_paths") as defaults:
            defaults.return_value = mock.sentinel.paths
            paths = resolve_provider_archive_paths(provider)

        defaults.assert_called_once_with(archive_directory_name="Synthetic Archive")
        self.assertIs(paths, mock.sentinel.paths)

    def test_ingest_source_bundle_calls_provider_importer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            source = Path(temp_name) / "synthetic.json"
            source.write_text("{}", encoding="utf-8")
            importer = mock.Mock(return_value=mock.sentinel.provider_result)
            provider = self._provider(importer)
            progress = mock.Mock()

            result = ingest_source_bundle(
                provider,
                source,
                archive_root=root,
                progress=progress,
            )

        importer.assert_called_once_with(
            source.resolve(),
            archive_root=root.resolve(),
            progress=progress,
        )
        self.assertEqual(result.provider_key, "synthetic")
        self.assertEqual(result.source_bundle, source.resolve())
        self.assertEqual(result.paths.root, root.resolve())
        self.assertIs(result.provider_result, mock.sentinel.provider_result)

    def test_ingest_source_bundle_rejects_missing_source(self) -> None:
        provider = self._provider(mock.Mock())

        with self.assertRaises(FileNotFoundError):
            ingest_source_bundle(provider, Path("definitely-missing-source.json"))

    def test_ingest_source_bundle_rejects_empty_source(self) -> None:
        provider = self._provider(mock.Mock())
        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "synthetic.json"
            source.write_bytes(b"")

            with self.assertRaises(ValueError):
                ingest_source_bundle(provider, source)


if __name__ == "__main__":
    unittest.main()
