import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gpt_exporter_gui as gui


class IndexSyncWorkflowTests(unittest.TestCase):
    def test_gui_index_helper_uses_open_database_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            database_path = archive_root / "conversations-index.sqlite"

            with mock.patch.object(
                gui,
                "update_archive_index",
                return_value=mock.sentinel.index_result,
            ) as update_index:
                result = gui.update_browser_index(database_path)

            self.assertIs(result, mock.sentinel.index_result)
            update_index.assert_called_once_with(
                archive_root.resolve(),
                downloads_dir=(archive_root / "downloads").resolve(),
                database_path=database_path.resolve(),
                progress=None,
            )

    def test_gui_archive_dialog_uses_current_workspace_and_provider_workflow(self) -> None:
        bundle = Path("C:/synthetic/Downloads/chatgpt-archive-source.json")
        workspace = gui.BUILTIN_WORKSPACES.get("chatgpt")
        provider_workflow = mock.Mock()
        provider_workflow.find_source_bundle.return_value = bundle

        app = mock.Mock()
        app.current_workspace = workspace
        app.provider_workflow = provider_workflow
        app.status_var = mock.Mock()
        app._archive_run_succeeded = mock.Mock(return_value=True)

        with mock.patch.object(gui, "WorkspaceArchiveRunDialog") as archive_dialog:
            started = gui.GPTExporterApp.process_downloaded_bundle(app)

        self.assertTrue(started)
        provider_workflow.find_source_bundle.assert_called_once_with()
        archive_dialog.assert_called_once_with(
            app,
            workspace=workspace,
            provider_workflow=provider_workflow,
            source_bundle=bundle,
            legacy_root=gui.ROOT,
            on_success=app._archive_run_succeeded,
        )
        app.status_var.set.assert_called_once_with(
            f"Archive bundle ready: {bundle.name}"
        )


if __name__ == "__main__":
    unittest.main()
