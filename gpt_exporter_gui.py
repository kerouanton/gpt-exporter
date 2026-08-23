import argparse
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import archive_browser as browser
import archive_gui_workflow as workflow


class GPTExporterApp(browser.ArchiveBrowser):
    """Archive Browser extended with the v2.8 archive workflow."""

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open DOCX", command=self.open_selected_docx)
        file_menu.add_command(label="Open in Explorer", command=self.open_selected_in_explorer)
        file_menu.add_separator()
        file_menu.add_command(label="Refresh", command=self._refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        archive_menu = tk.Menu(menu_bar, tearoff=False)
        archive_menu.add_command(
            label="Archive New Conversations…",
            command=self.archive_new_conversations,
        )
        archive_menu.add_separator()
        archive_menu.add_command(label="Open ChatGPT", command=self.open_chatgpt)
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
        help_menu.add_command(label="Search Syntax…", command=self.show_search_syntax)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu_bar)

    def archive_new_conversations(self) -> None:
        workflow.ArchiveWorkflowDialog(
            self,
            on_open_chatgpt=self.open_chatgpt,
            on_copy_collector=self.copy_collector_javascript,
            on_run_archive=self.process_downloaded_bundle,
        )

    def open_chatgpt(self) -> None:
        try:
            opened = workflow.open_chatgpt()
        except OSError as error:
            messagebox.showerror("Open ChatGPT", str(error), parent=self)
            return
        if not opened:
            messagebox.showwarning(
                "Open ChatGPT",
                "The default browser did not report that it opened ChatGPT.",
                parent=self,
            )

    def copy_collector_javascript(self) -> bool:
        try:
            source = workflow.read_collector_source()
            self.clipboard_clear()
            self.clipboard_append(source)
            self.update_idletasks()
        except (OSError, ValueError, tk.TclError) as error:
            messagebox.showerror("Copy Collector JavaScript", str(error), parent=self)
            return False
        self.status_var.set("Collector JavaScript copied to the clipboard.")
        return True

    def show_collector_in_explorer(self) -> None:
        try:
            browser.reveal_in_file_manager(str(workflow.COLLECTOR_PATH))
        except OSError as error:
            messagebox.showerror("Show Collector JavaScript", str(error), parent=self)

    def open_archive_folder(self) -> None:
        try:
            browser.open_with_default_application(str(self.database_path.parent))
        except OSError as error:
            messagebox.showerror("Open Archive Folder", str(error), parent=self)

    def process_downloaded_bundle(self) -> bool:
        bundle = workflow.find_latest_source_bundle()
        if bundle is None:
            messagebox.showinfo(
                "Process Downloaded Bundle",
                "No non-empty chatgpt-archive-source.json was found in the usual Downloads folders.\n\n"
                "Run the collector in ChatGPT first, or use Archive → Archive New Conversations… for guided instructions.",
                parent=self,
            )
            return False

        expected_database = browser.DEFAULT_DATABASE_PATH.resolve()
        try:
            current_database = self.database_path.resolve()
        except OSError:
            current_database = self.database_path
        if current_database != expected_database:
            messagebox.showerror(
                "Process Downloaded Bundle",
                "The v2.8 archive workflow currently targets the default archive under Documents. "
                "This Browser instance is using a different SQLite database, so the workflow was not started.",
                parent=self,
            )
            return False

        self.status_var.set(f"Archive bundle ready: {bundle.name}")
        workflow.ArchiveRunDialog(self, on_success=self._archive_run_succeeded)
        return True

    def _archive_run_succeeded(self) -> None:
        try:
            self._validate_database()
            self._refresh_all()
        except (OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror(
                "Archive Workflow",
                f"The archive completed, but the Browser could not reload the updated index:\n\n{error}",
                parent=self,
            )
            return
        self.status_var.set("Archive updated successfully and Browser refreshed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GPT Exporter graphical archive, index and browsing application"
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
        default=browser.DEBUG,
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
        messagebox.showerror("GPT Exporter", str(error), parent=root)
        root.destroy()
        return 1

    app.title("GPT Exporter")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
