"""ChatGPT actions injected into the shared conversation workspace shell."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tkinter import messagebox

from gpt_exporter.providers.gpt.ui import archive_workflow as workflow
from gpt_exporter.ui.archive_workflow import ArchiveWorkflowDialog, ArchiveWorkflowSpec
from gpt_exporter.ui.browser import archive_browser as browser
from gpt_exporter.workspaces import ConversationWorkspace


class GPTWorkspaceActions:
    service_label = "ChatGPT"
    process_label = "Process Downloaded Bundle…"
    regenerate_label = "Regenerate Missing DOCX…"
    can_regenerate = True
    archive_workflow_spec = ArchiveWorkflowSpec(
        service_label="ChatGPT",
        open_instructions="Open ChatGPT in your normal browser and make sure you are signed in.",
        collector_instructions=(
            "The collector JavaScript is copied to the clipboard automatically. "
            "Open Developer Tools (F12), select Console, paste it and run it."
        ),
        download_instructions=(
            "When the collector finishes, the browser downloads chatgpt-archive-source.json. "
            "As soon as a new non-empty bundle is detected, the archive workflow starts automatically."
        ),
        waiting_text="Waiting for a new chatgpt-archive-source.json in Downloads…",
    )

    def __init__(self, app, workspace: ConversationWorkspace) -> None:
        self.app = app
        self.workspace = workspace

    def archive_new(self) -> None:
        ArchiveWorkflowDialog(self.app, actions=self)

    def snapshot_exports(self):
        return workflow.source_bundle_signature(workflow.find_latest_source_bundle())

    def find_new_export(self, snapshot) -> Path | None:
        bundle = workflow.find_latest_source_bundle()
        if bundle is None:
            return None
        signature = workflow.source_bundle_signature(bundle)
        if signature == snapshot:
            return None
        return bundle

    def open_service(self) -> None:
        try:
            opened = workflow.open_chatgpt()
        except OSError as error:
            messagebox.showerror("Open ChatGPT", str(error), parent=self.app)
            return
        if not opened:
            messagebox.showwarning(
                "Open ChatGPT",
                "The default browser did not report that it opened ChatGPT.",
                parent=self.app,
            )

    def copy_collector(self) -> bool:
        try:
            source = workflow.read_collector_source()
            self.app.clipboard_clear()
            self.app.clipboard_append(source)
            self.app.update_idletasks()
        except Exception as error:
            messagebox.showerror("Copy Collector JavaScript", str(error), parent=self.app)
            return False
        self.app.status_var.set("Collector JavaScript copied to the clipboard.")
        return True

    def show_collector(self) -> None:
        try:
            browser.reveal_in_file_manager(str(workflow.COLLECTOR_PATH))
        except OSError as error:
            messagebox.showerror("Show Collector JavaScript", str(error), parent=self.app)

    def process_export(self, path: Path) -> bool:
        bundle = Path(path)
        try:
            if not bundle.is_file() or bundle.stat().st_size <= 0:
                return False
        except OSError:
            return False

        self.app.status_var.set(f"Archive bundle ready: {bundle.name}")
        workflow.ArchiveRunDialog(
            self.app,
            archive_root=self.workspace.root_path,
            source_bundle=bundle,
            on_success=lambda: self._archive_succeeded("ChatGPT archive updated."),
            log_directory=self.workspace.root_path / "reports",
        )
        return True

    def process_downloaded(self) -> bool:
        bundle = workflow.find_latest_source_bundle()
        if bundle is None:
            messagebox.showinfo(
                "Process Downloaded Bundle",
                "No non-empty chatgpt-archive-source.json was found in the usual Downloads folders.\n\n"
                "Run the collector in ChatGPT first.",
                parent=self.app,
            )
            return False
        return self.process_export(bundle)

    def regenerate_missing(self) -> bool:
        try:
            missing = workflow.find_missing_docx_sources(self.workspace.root_path)
        except OSError as error:
            messagebox.showerror("Regenerate Missing DOCX", str(error), parent=self.app)
            return False

        if not missing:
            messagebox.showinfo(
                "Regenerate Missing DOCX",
                "All archived conversations already have a non-empty DOCX export.",
                parent=self.app,
            )
            return False

        self.app.status_var.set(f"Missing DOCX exports detected: {len(missing)}")
        workflow.MissingDocxRepairDialog(
            self.app,
            archive_root=self.workspace.root_path,
            on_success=lambda: self._archive_succeeded("Missing DOCX exports regenerated."),
        )
        return True

    def show_last_log(self) -> None:
        log_path = workflow.latest_archive_log_path(self.workspace.root_path / "reports")
        if not log_path.is_file():
            messagebox.showinfo(
                "Show Last Archive Log",
                "No persistent archive-workflow log is available yet.",
                parent=self.app,
            )
            return
        try:
            browser.open_with_default_application(str(log_path))
        except OSError as error:
            messagebox.showerror("Show Last Archive Log", str(error), parent=self.app)

    def _archive_succeeded(self, message: str) -> bool:
        try:
            self.app.provider_content_changed(message)
        except (OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror(
                "Archive Workflow",
                f"The archive completed, but the shared Browser could not reload the index:\n\n{error}",
                parent=self.app,
            )
            return False
        return True


__all__ = ["GPTWorkspaceActions"]
