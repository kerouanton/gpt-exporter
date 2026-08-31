import json
import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.provider_pipeline import archive_provider_bundle
from gpt_exporter.providers.base import ExporterProvider


class ProviderPipelineTests(unittest.TestCase):
    def _provider(self, importer) -> ExporterProvider:
        return ExporterProvider(
            key="chatgpt",
            display_name="Synthetic ChatGPT",
            archive_directory_name="Synthetic Archive",
            website_url="https://example.invalid/",
            source_bundle_name="synthetic-source.json",
            collector_path=Path(__file__),
            importer=importer,
            normalizer=mock.Mock(),
        )

    def test_pipeline_imports_through_provider_and_preserves_current_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            source = Path(temp_name) / "synthetic-source.json"
            source.write_text("{}", encoding="utf-8")

            def importer(bundle_path, *, archive_root, progress=None):
                archive = Path(archive_root)
                (archive / "downloads").mkdir(parents=True, exist_ok=True)
                (archive / "reports").mkdir(parents=True, exist_ok=True)
                conversation = archive / "downloads" / "conv.json.xz"
                conversation.write_bytes(b"synthetic")
                (archive / "reports" / "current-batch.json").write_text(
                    json.dumps({"conversation_files": [conversation.name]}),
                    encoding="utf-8",
                )
                return SimpleNamespace(success=True)

            provider = self._provider(mock.Mock(side_effect=importer))
            export_result = SimpleNamespace(success=True)
            index_result = SimpleNamespace()

            with (
                mock.patch("gpt_exporter.provider_pipeline.inventory_media", return_value=SimpleNamespace()),
                mock.patch("gpt_exporter.provider_pipeline.render_inventory_summary", return_value="inventory"),
                mock.patch("gpt_exporter.provider_pipeline.build_asset_manifest", return_value=SimpleNamespace()),
                mock.patch("gpt_exporter.provider_pipeline.render_manifest_summary", return_value="manifest"),
                mock.patch("gpt_exporter.provider_pipeline.export_batch", return_value=export_result) as export_batch,
                mock.patch("gpt_exporter.provider_pipeline.update_archive_index", return_value=index_result),
            ):
                result = archive_provider_bundle(
                    provider,
                    archive_root=root,
                    source_bundle=source,
                    delete_source=False,
                )

            provider.importer.assert_called_once()
            export_batch.assert_called_once()
            _, export_kwargs = export_batch.call_args
            self.assertEqual(export_kwargs["batch_file"], root / "reports" / "current-batch.json")
            self.assertFalse(result.export_skipped)
            self.assertIs(result.export_result, export_result)

    def test_empty_current_batch_skips_export_but_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            source = Path(temp_name) / "synthetic-source.json"
            source.write_text("{}", encoding="utf-8")

            def importer(bundle_path, *, archive_root, progress=None):
                archive = Path(archive_root)
                (archive / "downloads").mkdir(parents=True, exist_ok=True)
                (archive / "reports").mkdir(parents=True, exist_ok=True)
                (archive / "downloads" / "existing.json.xz").write_bytes(b"synthetic")
                (archive / "reports" / "current-batch.json").write_text(
                    json.dumps({"conversation_files": []}),
                    encoding="utf-8",
                )
                return SimpleNamespace(success=True)

            provider = self._provider(importer)
            index_result = SimpleNamespace()

            with (
                mock.patch("gpt_exporter.provider_pipeline.inventory_media", return_value=SimpleNamespace()),
                mock.patch("gpt_exporter.provider_pipeline.render_inventory_summary", return_value="inventory"),
                mock.patch("gpt_exporter.provider_pipeline.build_asset_manifest", return_value=SimpleNamespace()),
                mock.patch("gpt_exporter.provider_pipeline.render_manifest_summary", return_value="manifest"),
                mock.patch("gpt_exporter.provider_pipeline.export_batch") as export_batch,
                mock.patch("gpt_exporter.provider_pipeline.update_archive_index", return_value=index_result) as update_index,
            ):
                result = archive_provider_bundle(
                    provider,
                    archive_root=root,
                    source_bundle=source,
                    delete_source=False,
                )

            export_batch.assert_not_called()
            update_index.assert_called_once()
            self.assertTrue(result.export_skipped)
            self.assertIsNone(result.export_result)

    def test_non_chatgpt_provider_is_rejected_before_archive_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            provider = ExporterProvider(
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
                archive_provider_bundle(provider, archive_root=root, convert_only=True)

            self.assertFalse(root.exists())
            provider.importer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
