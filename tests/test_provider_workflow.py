import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.providers import CHATGPT_PROVIDER
from gpt_exporter.providers.base import ExporterProvider
from gpt_exporter.workflow import ProviderWorkflow, WorkspaceWorkflow
from gpt_exporter.workspaces import Workspace


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

    def test_workspace_workflow_always_uses_workspace_provider_and_archive_root(self) -> None:
        workspace = Workspace(
            key="chatgpt-test",
            display_name="ChatGPT Test",
            provider=CHATGPT_PROVIDER,
            archive_root=Path("C:/synthetic/ChatGPT Test Archive"),
        )
        workflow = WorkspaceWorkflow(workspace)
        source = Path("C:/synthetic/Downloads/chatgpt-archive-source.json")

        with mock.patch("gpt_exporter.workflow.archive_bundle", return_value=mock.sentinel.result) as archive:
            result = workflow.run_archive(source_bundle=source, delete_source=False)

        archive.assert_called_once()
        args, kwargs = archive.call_args
        self.assertIs(args[0], CHATGPT_PROVIDER)
        self.assertEqual(kwargs["archive_root"], workspace.archive_root)
        self.assertEqual(kwargs["source_bundle"], source)
        self.assertFalse(kwargs["delete_source"])
        self.assertIs(result, mock.sentinel.result)

    def test_workspace_workflow_updates_its_own_core_index(self) -> None:
        workspace = Workspace(
            key="chatgpt-test",
            display_name="ChatGPT Test",
            provider=CHATGPT_PROVIDER,
            archive_root=Path("C:/synthetic/ChatGPT Test Archive"),
        )
        workflow = WorkspaceWorkflow(workspace)

        with mock.patch(
            "gpt_exporter.workflow.update_normalized_index",
            return_value=mock.sentinel.index_result,
        ) as update_index:
            result = workflow.update_index(force=True, progress=mock.sentinel.progress)

        update_index.assert_called_once_with(
            CHATGPT_PROVIDER,
            workspace.archive_root,
            downloads_dir=workspace.paths.downloads,
            database_path=workspace.database_path,
            force=True,
            progress=mock.sentinel.progress,
        )
        self.assertIs(result, mock.sentinel.index_result)

    def test_workspace_workflow_exposes_workspace_paths(self) -> None:
        workspace = Workspace(
            key="chatgpt-test",
            display_name="ChatGPT Test",
            provider=CHATGPT_PROVIDER,
            archive_root=Path("C:/synthetic/ChatGPT Test Archive"),
        )
        workflow = WorkspaceWorkflow(workspace)

        self.assertIs(workflow.provider, CHATGPT_PROVIDER)
        self.assertEqual(workflow.archive_root, workspace.archive_root)
        self.assertEqual(workflow.paths.database, workspace.database_path)
        self.assertEqual(workflow.database_path, workspace.database_path)

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
