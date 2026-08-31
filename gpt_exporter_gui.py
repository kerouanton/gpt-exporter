import argparse
import contextlib
import io
import os
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk


def _ensure_standard_streams() -> None:
    """Provide harmless sinks when Windows windowed mode has no stdio streams."""

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_ensure_standard_streams()

# The historical browser remains directly executable and prints its filename
# when imported. GPT Exporter imports it as an implementation module, so keep
# that compatibility diagnostic out of the application's own output surface.
with contextlib.redirect_stdout(io.StringIO()):
    import archive_browser as browser

import archive_gui_workflow as legacy_workflow
from gpt_exporter.index import IndexUpdateResult, update_index as update_archive_index
from gpt_exporter.providers import BUILTIN_PROVIDERS, CHATGPT_PROVIDER
from gpt_exporter.resources import read_release_history, read_user_guide
from gpt_exporter.ui import (
    WorkspaceArchiveDialog,
    WorkspaceArchiveRunDialog,
    latest_archive_log_path,
    show_about_dialog,
    show_markdown_document,
    show_provider_manager,
)
from gpt_exporter.version import APP_NAME, display_version
from gpt_exporter.workflow import ProviderWorkflow
from gpt_exporter.workspaces import BUILTIN_WORKSPACES, Workspace, WorkspaceRegistry


ROOT = Path(__file__).resolve().parent


def update_browser_index(
    database_path: Path,
    *,
    progress=None,
) -> IndexUpdateResult:
    """Update the Browser's open archive database through the library API."""
    database_path = Path(database_path).expanduser().resolve()
    archive_root = database_path.parent
    return update_archive_index(
        archive_root,
        downloads_dir=archive_root / "downloads",
        database_path=database_path,
        progress=progress,
    )


def _workspace_for_database(
    database_path: Path,
    workspaces: WorkspaceRegistry,
) -> Workspace:
    """Resolve a configured workspace or preserve --database as a custom ChatGPT workspace."""
    database = Path(database_path).expanduser().resolve()
    for workspace in workspaces.all():
        if workspace.database_path == database:
            return workspace
    return Workspace(
        key="custom-chatgpt",
        display_name="ChatGPT (Custom Archive)",
        provider=CHATGPT_PROVIDER,
        archive_root=database.parent,
    )


class GPTExporterApp(browser.ArchiveBrowser):
    """Exporter-core browser operating on one selected workspace."""

    def __init__(
        self,
        database_path: Path,
        *,
        debug: bool = False,
        workspace_registry: WorkspaceRegistry = BUILTIN_WORKSPACES,
    ) -> None:
        self.workspace_registry = workspace_registry
        self.current_workspace = _workspace_for_database(database_path, workspace_registry)
        self.provider_workflow = ProviderWorkflow(self.current_workspace.provider)
        self.available_workspaces = list(workspace_registry.all())
        if all(item.key != self.current_workspace.key for item in self.available_workspaces):
            self.available_workspaces.append(self.current_workspace)
        super().__init__(self.current_workspace.database_path, debug=debug)
        self._install_workspace_selector()
        self._update_workspace_identity()

    def _build_menu(self) -> None:
        provider = self.current_workspace.provider
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open DOCX", command=self.open_selected_docx)
        file_menu.add_command(label="Open in Explorer", command=self.open_selected_in_explorer)
        file_menu.add_separator()
        file_menu.add_command(label="Refresh", command=self._refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        providers_menu = tk.Menu(menu_bar, tearoff=False)
        providers_menu.add_command(label="Manage Providers…", command=self.manage_providers)
        menu_bar.add_cascade(label="Providers", menu=providers_menu)

        archive_menu = tk.Menu(menu_bar, tearoff=False)
        archive_menu.add_command(
            label="Archive New Conversations…",
            command=self.archive_new_conversations,
        )
        archive_menu.add_separator()
        archive_menu.add_command(
            label=f"Open {provider.display_name}",
            command=self.open_provider,
        )
        archive_menu.add_command(
            label="Copy Collector JavaScript",
            command=self.copy_collector_javascript,
        )
        archive_menu.add_command(
            label="Show Collector JavaScript in Explorer",
            command=self.show_collector_in_explorer,
        )
        archive_menu.add_command(
            label="Process Downloaded Bundle…",
            command=self.process_downloaded_bundle,
        )
        archive_menu.add_separator()
        archive_menu.add_command(label="Update Search Index", command=self.update_index)
        archive_menu.add_command(label="Open Archive Folder", command=self.open_archive_folder)
        archive_menu.add_command(label="Show Last Archive Log", command=self.show_last_archive_log)
        menu_bar.add_cascade(label="Archive", menu=archive_menu)

        project_menu = tk.Menu(menu_bar, tearoff=False)
        project_menu.add_command(label="New Project…", command=self.new_project)
        project_menu.add_command(label="Add Sub-project…", command=self.add_subproject)
        project_menu.add_command(label="Rename Selected Branch…", command=self.rename_selected_project)
        project_menu.add_command(label="Delete Selected Branch…", command=self.delete_selected_project)
        project_menu.add_separator()
        project_menu.add_command(label="Assign Selected Conversation…", command=self.assign_selected_conversation)
        project_menu.add_command(
            label="Remove Selected Project Assignment",
            command=self.remove_selected_project_assignment,
        )
        menu_bar.add_cascade(label="Project", menu=project_menu)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Clear Filters", command=self._clear_filters)
        view_menu.add_command(label="Refresh All", command=self._refresh_all)
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="User Guide…", command=self.show_user_guide)
        help_menu.add_command(label="Release History…", command=self.show_release_history)
        help_menu.add_command(label="Search Syntax…", command=self.show_search_syntax)
        help_menu.add_separator()
        help_menu.add_command(label="About GPT Exporter…", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu_bar)

    def _install_workspace_selector(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6, 8, 0))
        children = self.winfo_children()
        if children:
            bar.pack(fill="x", before=children[0])
        else:
            bar.pack(fill="x")

        ttk.Label(bar, text="Workspace:").pack(side="left")
        self.workspace_var = tk.StringVar(value=self.current_workspace.display_name)
        self.workspace_combo = ttk.Combobox(
            bar,
            textvariable=self.workspace_var,
            values=[item.display_name for item in self.available_workspaces],
            state="readonly",
            width=30,
        )
        self.workspace_combo.pack(side="left", padx=(6, 10))
        self.workspace_combo.bind("<<ComboboxSelected>>", self._workspace_selected)
        self.workspace_path_var = tk.StringVar(value=str(self.current_workspace.archive_root))
        ttk.Label(bar, textvariable=self.workspace_path_var).pack(side="left", fill="x", expand=True)

    def _workspace_selected(self, _event=None) -> None:
        selected_name = self.workspace_var.get()
        target = next(
            (item for item in self.available_workspaces if item.display_name == selected_name),
            None,
        )
        if target is None or target.key == self.current_workspace.key:
            return

        old_workspace = self.current_workspace
        old_database = self.database_path
        self.current_workspace = target
        self.provider_workflow = ProviderWorkflow(target.provider)
        self.database_path = target.database_path
        try:
            self._validate_database()
            self._clear_filters()
            self._refresh_all()
        except (OSError, ValueError, sqlite3.Error) as error:
            self.current_workspace = old_workspace
            self.provider_workflow = ProviderWorkflow(old_workspace.provider)
            self.database_path = old_database
            self.workspace_var.set(old_workspace.display_name)
            messagebox.showerror(
                "Switch Workspace",
                f"The workspace could not be opened:\n\n{target.archive_root}\n\n{error}",
                parent=self,
            )
            return

        self._build_menu()
        self._update_workspace_identity()
        self.status_var.set(f"Workspace switched to {target.display_name}.")

    def _update_workspace_identity(self) -> None:
        if hasattr(self, "workspace_var"):
            self.workspace_var.set(self.current_workspace.display_name)
        if hasattr(self, "workspace_path_var"):
            self.workspace_path_var.set(str(self.current_workspace.archive_root))
        self.title(f"{APP_NAME} — {self.current_workspace.display_name}")

    def manage_providers(self) -> None:
        """Open the exporter-core provider registry UI."""
        show_provider_manager(self, BUILTIN_PROVIDERS)

    def show_user_guide(self) -> None:
        self._show_markdown_resource("GPT Exporter User Guide", read_user_guide)

    def show_release_history(self) -> None:
        self._show_markdown_resource("GPT Exporter Release History", read_release_history)

    def _show_markdown_resource(self, title: str, reader) -> None:
        try:
            markdown = reader()
        except (OSError, ValueError) as error:
            messagebox.showerror(title, str(error), parent=self)
            return
        show_markdown_document(self, title=title, markdown=markdown)

    def show_about(self) -> None:
        show_about_dialog(
            self,
            on_user_guide=self.show_user_guide,
            on_history=self.show_release_history,
        )

    def archive_new_conversations(self) -> None:
        WorkspaceArchiveDialog(
            self,
            workspace=self.current_workspace,
            find_source_bundle=lambda: self.provider_workflow.find_source_bundle(),
            source_bundle_signature=legacy_workflow.source_bundle_signature,
            on_open_provider=self.open_provider,
            on_copy_collector=self.copy_collector_javascript,
            on_run_archive=self.process_downloaded_bundle,
        )

    def open_provider(self) -> None:
        provider = self.current_workspace.provider
        title = f"Open {provider.display_name}"
        try:
            opened = self.provider_workflow.open_website()
        except OSError as error:
            messagebox.showerror(title, str(error), parent=self)
            return
        if not opened:
            messagebox.showwarning(
                title,
                f"The default browser did not report that it opened {provider.display_name}.",
                parent=self,
            )

    def open_chatgpt(self) -> None:
        """Compatibility wrapper retained for external callers during migration."""
        self.open_provider()

    def copy_collector_javascript(self) -> bool:
        try:
            source = self.provider_workflow.read_collector_source()
            self.clipboard_clear()
            self.clipboard_append(source)
            self.update_idletasks()
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("Copy Collector JavaScript", str(error), parent=self)
            return False
        self.status_var.set(
            f"{self.current_workspace.provider.display_name} collector JavaScript copied to the clipboard."
        )
        return True

    def show_collector_in_explorer(self) -> None:
        try:
            browser.reveal_in_file_manager(str(self.current_workspace.provider.collector_path))
        except OSError as error:
            messagebox.showerror("Show Collector JavaScript", str(error), parent=self)

    def open_archive_folder(self) -> None:
        try:
            browser.open_with_default_application(str(self.current_workspace.archive_root))
        except OSError as error:
            messagebox.showerror("Open Archive Folder", str(error), parent=self)

    def show_last_archive_log(self) -> None:
        log_path = latest_archive_log_path(self.current_workspace.paths.reports)
        if not log_path.is_file():
            messagebox.showinfo(
                "Show Last Archive Log",
                "No persistent archive-workflow log is available yet.",
                parent=self,
            )
            return
        try:
            browser.open_with_default_application(str(log_path))
        except OSError as error:
            messagebox.showerror("Show Last Archive Log", str(error), parent=self)

    def update_index(self) -> None:
        """Update the current workspace Browser index through the reusable library."""
        browser.LOGGER.info(
            "Updating archive search index in-process for workspace %s",
            self.current_workspace.key,
        )
        self.status_var.set("Updating search index…")
        self.update_idletasks()

        try:
            result = update_browser_index(
                self.database_path,
                progress=lambda message: browser.LOGGER.info("Indexer: %s", message),
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            browser.LOGGER.exception("Unable to update index: %s", error)
            self.status_var.set("Index update failed.")
            messagebox.showerror("Update Search Index", str(error), parent=self)
            return

        if result.failed:
            browser.LOGGER.warning(
                "Index update completed with %d source failure(s).",
                result.failed,
            )

        self._validate_database()
        self._refresh_all()
        messagebox.showinfo(
            "Update Search Index",
            "Search index updated successfully.",
            parent=self,
        )

    def process_downloaded_bundle(self) -> bool:
        provider = self.current_workspace.provider
        bundle = self.provider_workflow.find_source_bundle()
        if bundle is None:
            messagebox.showinfo(
                "Process Downloaded Bundle",
                f"No non-empty {provider.source_bundle_name} was found in the usual Downloads folders.\n\n"
                f"Run the collector in {provider.display_name} first, or use Archive → Archive New Conversations… for guided instructions.",
                parent=self,
            )
            return False

        self.status_var.set(f"Archive bundle ready: {bundle.name}")
        WorkspaceArchiveRunDialog(
            self,
            workspace=self.current_workspace,
            provider_workflow=self.provider_workflow,
            source_bundle=bundle,
            legacy_root=ROOT,
            on_success=self._archive_run_succeeded,
        )
        return True

    def _archive_run_succeeded(self) -> bool:
        try:
            self._validate_database()
            self._refresh_all()
        except (OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror(
                "Archive Workflow",
                f"The archive completed, but the Browser could not reload the updated index:\n\n{error}",
                parent=self,
            )
            return False
        self.status_var.set(
            f"{self.current_workspace.display_name} archive updated successfully and Browser refreshed."
        )
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GPT Exporter graphical archive, index and browsing application"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {display_version()}",
        help="Show the application version and exit.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=browser.DEFAULT_DATABASE_PATH,
        help=f"SQLite index path (default: {browser.DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable verbose debug logging.",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    browser.configure_logging(arguments.debug)
    browser.LOGGER.debug("GUI arguments: %s", arguments)

    try:
        app = GPTExporterApp(arguments.database, debug=arguments.debug)
    except (OSError, ValueError, sqlite3.Error) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, str(error), parent=root)
        root.destroy()
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
