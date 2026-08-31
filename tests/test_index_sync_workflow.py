import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import gpt_exporter_gui as gui


class IndexSyncWorkflowTests(unittest.TestCase):
    def test_gui_index_update_uses_current_workspace_workflow(self) -> None:
        app = mock.Mock()
        app.current_workspace = SimpleNamespace(key="chatgpt-test")
        app.workspace_workflow = mock.Mock()
        app.workspace_workflow.update_index.return_value = SimpleNamespace(failed=0)
        app.status_var = mock.Mock()
        app.update_idletasks = mock.Mock()
        app._validate_database = mock.Mock()
        app._refresh_all = mock.Mock()

        with mock.patch.object(gui.messagebox, "showinfo") as showinfo:
            gui.GPTExporterApp.update_index(app)

        app.workspace_workflow.update_index.assert_called_once()
        self.assertIn("progress", app.workspace_workflow.update_index.call_args.kwargs)
        app._validate_database.assert_called_once_with()
        app._refresh_all.assert_called_once_with()
        showinfo.assert_called_once_with(
            "Update Search Index",
            "Search index updated successfully.",
            parent=app,
        )

    def test_gui_archive_dialog_uses_current_workspace_workflow(self) -> None:
        bundle = Path("C:/synthetic/Downloads/chatgpt-archive-source.json")
        workspace = gui.BUILTIN_WORKSPACES.get("chatgpt")
        workspace_workflow = mock.Mock()
        workspace_workflow.provider = workspace.provider
        workspace_workflow.find_source_bundle.return_value = bundle

        app = mock.Mock()
        app.current_workspace = workspace
        app.workspace_workflow = workspace_workflow
        app.status_var = mock.Mock()
        app._archive_run_succeeded = mock.Mock(return_value=True)

        with mock.patch.object(gui, "WorkspaceArchiveRunDialog") as archive_dialog:
            started = gui.GPTExporterApp.process_downloaded_bundle(app)

        self.assertTrue(started)
        workspace_workflow.find_source_bundle.assert_called_once_with()
        archive_dialog.assert_called_once_with(
            app,
            workspace_workflow=workspace_workflow,
            source_bundle=bundle,
            legacy_root=gui.ROOT,
            on_success=app._archive_run_succeeded,
        )
        app.status_var.set.assert_called_once_with(
            f"Archive bundle ready: {bundle.name}"
        )


if __name__ == "__main__":
    unittest.main()
