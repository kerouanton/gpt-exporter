"""Single provider-neutral conversation browser shell for named workspaces."""

from __future__ import annotations

import sqlite3
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Protocol

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.index import update_index as update_archive_index
from gpt_exporter.resources import read_release_history, read_user_guide
from gpt_exporter.ui import show_about_dialog, show_markdown_document
from gpt_exporter.ui.browser import archive_browser as browser
from gpt_exporter.ui.workspace_selector import choose_workspace
from gpt_exporter.version import APP_NAME
from gpt_exporter.workspaces import ConversationWorkspace, WorkspaceCatalog


class WorkspaceActions(Protocol):
    """Provider-owned commands injected into the common shell."""

    service_label: str
    process_label: str
    regenerate_label: str
    can_regenerate: bool

    def archive_new(self) -> None: ...
    def open_service(self) -> None: ...
    def copy_collector(self) -> None: ...
    def show_collector(self) -> None: ...
    def process_downloaded(self) -> None: ...
    def regenerate_missing(self) -> None: ...
    def show_last_log(self) -> None: ...


ActionFactory = Callable[["ConversationWorkspaceApp", ConversationWorkspace], WorkspaceActions]


def ensure_workspace_index(workspace: ConversationWorkspace) -> None:
    """Create/update the shared SQLite index for one workspace."""
    workspace.root_path.mkdir(parents=True, exist_ok=True)
    update_archive_index(
        workspace.root_path,
        downloads_dir=workspace.root_path / "downloads",
        database_path=workspace.database_path,
    )


class ConversationWorkspaceApp(browser.ArchiveBrowser):
    """The one conversation UI used for every workspace and provider."""

    def __init__(
        self,
        *,
        catalog: WorkspaceCatalog,
        registry: ProviderRegistry,
        workspace: ConversationWorkspace,
        action_factory: ActionFactory,
        debug: bool = False,
    ) -> None:
        self.workspace_catalog = catalog
        self.provider_registry = registry
        self.workspace = workspace
        self.action_factory = action_factory
        self.provider_actions: WorkspaceActions | None = None
        self.workspace_var: tk.StringVar | None = None
        self.workspace_provider_var: tk.StringVar | None = None
        self.workspace_root_var: tk.StringVar | None = None
        self._archive_menu: tk.Menu | None = None
        self._service_menu_index: int | None = None
        self._process_menu_index: int | None = None
        self._regenerate_menu_index: int | None = None

        ensure_workspace_index(workspace)
        super().__init__(workspace.database_path, debug=debug)
        self.provider_actions = self.action_factory(self, workspace)
        self._refresh_workspace_chrome()
        self.title(APP_NAME)

    def _build_ui(self) -> None:
        workspace_bar = ttk.LabelFrame(self, text="Active Workspace", padding=(8, 6))
        workspace_bar.pack(fill="x", padx=8, pady=(8, 0))

        self.workspace_var = tk.StringVar(value=self.workspace.name)
        self.workspace_provider_var = tk.StringVar()
        self.workspace_root_var = tk.StringVar()

        ttk.Label(workspace_bar, text="Workspace:").grid(row=0, column=0, sticky="w")
        self.workspace_combo = ttk.Combobox(
            workspace_bar,
            textvariable=self.workspace_var,
            state="readonly",
            width=28,
        )
        self.workspace_combo.grid(row=0, column=1, sticky="w", padx=(6, 16))
        self.workspace_combo.bind("<<ComboboxSelected>>", self._workspace_combo_changed)

        ttk.Label(workspace_bar, text="Provider:").grid(row=0, column=2, sticky="w")
        ttk.Label(workspace_bar, textvariable=self.workspace_provider_var).grid(
            row=0, column=3, sticky="w", padx=(6, 16)
        )
        ttk.Label(workspace_bar, text="Root:").grid(row=0, column=4, sticky="w")
        ttk.Label(workspace_bar, textvariable=self.workspace_root_var).grid(
            row=0, column=5, sticky="ew", padx=(6, 0)
        )
        workspace_bar.columnconfigure(5, weight=1)

        super()._build_ui()
        self._refresh_workspace_values()

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

        workspace_menu = tk.Menu(menu_bar, tearoff=False)
        workspace_menu.add_command(label="Switch Workspace…", command=self.switch_workspace_dialog)
        workspace_menu.add_command(label="Inspect Active Workspace", command=self.inspect_active_workspace)
        workspace_menu.add_command(label="Refresh Workspace", command=self.refresh_active_workspace)
        workspace_menu.add_separator()
        workspace_menu.add_command(label="Open Workspace Folder", command=self.open_workspace_folder)
        menu_bar.add_cascade(label="Workspace", menu=workspace_menu)

        archive_menu = tk.Menu(menu_bar, tearoff=False)
        archive_menu.add_command(label="Archive New Conversations…", command=self.archive_new_conversations)
        archive_menu.add_separator()
        archive_menu.add_command(label="Open Service", command=self.open_provider_service)
        self._service_menu_index = archive_menu.index("end")
        archive_menu.add_command(label="Copy Collector JavaScript", command=self.copy_collector_javascript)
        archive_menu.add_command(label="Show Collector JavaScript in Explorer", command=self.show_collector_in_explorer)
        archive_menu.add_command(label="Process Downloaded Export…", command=self.process_downloaded_export)
        self._process_menu_index = archive_menu.index("end")
        archive_menu.add_command(label="Regenerate Missing DOCX…", command=self.regenerate_missing_docx)
        self._regenerate_menu_index = archive_menu.index("end")
        archive_menu.add_separator()
        archive_menu.add_command(label="Update Search Index", command=self.update_index)
        archive_menu.add_command(label="Open Archive Folder", command=self.open_workspace_folder)
        archive_menu.add_command(label="Show Last Archive Log", command=self.show_last_archive_log)
        menu_bar.add_cascade(label="Archive", menu=archive_menu)
        self._archive_menu = archive_menu

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
        help_menu.add_command(label=f"About {APP_NAME}…", command=self.show_about)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu_bar)

    def _enabled_workspaces(self) -> tuple[ConversationWorkspace, ...]:
        available = set(self.provider_registry.provider_ids())
        return tuple(
            item
            for item in self.workspace_catalog.list(enabled_only=True)
            if item.provider_id in available
        )

    def _refresh_workspace_values(self) -> None:
        if self.workspace_var is None:
            return
        values = tuple(item.name for item in self._enabled_workspaces())
        self.workspace_combo["values"] = values
        if self.workspace.name in values:
            self.workspace_var.set(self.workspace.name)

    def _provider_display_name(self, provider_id: str) -> str:
        try:
            return self.provider_registry.get(provider_id).descriptor.display_name
        except KeyError:
            return provider_id

    def _refresh_workspace_chrome(self) -> None:
        self._refresh_workspace_values()
        if self.workspace_provider_var is not None:
            self.workspace_provider_var.set(self._provider_display_name(self.workspace.provider_id))
        if self.workspace_root_var is not None:
            self.workspace_root_var.set(str(self.workspace.root_path))
        self.title(f"{APP_NAME} — {self.workspace.name}")

        actions = self.provider_actions
        if actions is None or self._archive_menu is None:
            return
        if self._service_menu_index is not None:
            self._archive_menu.entryconfigure(
                self._service_menu_index,
                label=f"Open {actions.service_label}",
            )
        if self._process_menu_index is not None:
            self._archive_menu.entryconfigure(self._process_menu_index, label=actions.process_label)
        if self._regenerate_menu_index is not None:
            self._archive_menu.entryconfigure(
                self._regenerate_menu_index,
                label=actions.regenerate_label,
                state="normal" if actions.can_regenerate else "disabled",
            )

    def _workspace_combo_changed(self, _event: tk.Event | None = None) -> None:
        if self.workspace_var is not None:
            self.switch_workspace(self.workspace_var.get())

    def switch_workspace_dialog(self) -> None:
        selected = choose_workspace(
            self._enabled_workspaces(),
            default_workspace_name=self.workspace.name,
            parent=self,
        )
        if selected:
            self.switch_workspace(selected)

    def switch_workspace(self, name: str) -> bool:
        if name == self.workspace.name:
            return True
        try:
            workspace = self.workspace_catalog.get(name)
            if not workspace.enabled:
                raise ValueError(f"Workspace '{name}' is disabled")
            self.provider_registry.get(workspace.provider_id)
            ensure_workspace_index(workspace)
            self.database_path = workspace.database_path
            self._validate_database()
        except (KeyError, OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror("Switch Workspace", str(error), parent=self)
            if self.workspace_var is not None:
                self.workspace_var.set(self.workspace.name)
            return False

        self.workspace_catalog.set_active(workspace.name)
        self.workspace = workspace
        self.provider_actions = self.action_factory(self, workspace)
        self.search_var.set("")
        self.origin_var.set(browser.ALL_VALUE)
        self.project_var.set(browser.ALL_VALUE)
        self.project_view = browser.PROJECT_VIEW_ALL
        self.tag_var.set(browser.ALL_VALUE)
        self.category_var.set(browser.ALL_VALUE)
        self._refresh_all()
        self._refresh_workspace_chrome()
        self.status_var.set(
            f"Workspace active: {workspace.name} — {self._provider_display_name(workspace.provider_id)}"
        )
        return True

    def _resolved_selected_docx_path(self) -> str | None:
        """Return the selected DOCX path, asking the provider only as a fallback.

        The browser itself stays provider-neutral. Older provider indexes may not
        have recorded a derived DOCX path, so a provider adapter can resolve its
        own historical naming convention without leaking that convention here.
        """
        row = self._selected_row()
        if not row:
            return None
        recorded = row.get("docx_path")
        if recorded:
            return str(recorded)

        resolver = getattr(self._actions(), "resolve_docx_path", None)
        if not callable(resolver):
            return None
        resolved = resolver(row)
        if resolved is None:
            return None
        path = Path(resolved)
        if not path.exists():
            return str(path)

        path_text = str(path)
        row["docx_path"] = path_text
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute(
                    "UPDATE conversations SET docx_path = ? WHERE conversation_id = ?",
                    (path_text, row["conversation_id"]),
                )
        except sqlite3.Error:
            browser.LOGGER.exception("Could not persist provider-resolved DOCX path")
        return path_text

    def open_selected_docx(self) -> None:
        try:
            browser.open_with_default_application(self._resolved_selected_docx_path())
        except OSError as error:
            messagebox.showerror("Open DOCX", str(error), parent=self)

    def open_selected_in_explorer(self) -> None:
        try:
            browser.reveal_in_file_manager(self._resolved_selected_docx_path())
        except OSError as error:
            messagebox.showerror("Open in Explorer", str(error), parent=self)

    def inspect_active_workspace(self) -> None:
        exists = self.workspace.database_path.is_file()
        messagebox.showinfo(
            "Active Workspace",
            f"Name: {self.workspace.name}\n"
            f"Provider: {self._provider_display_name(self.workspace.provider_id)} ({self.workspace.provider_id})\n"
            f"Root: {self.workspace.root_path}\n"
            f"Database: {self.workspace.database_path}\n"
            f"Database status: {'Present' if exists else 'Missing'}",
            parent=self,
        )

    def refresh_active_workspace(self) -> None:
        try:
            ensure_workspace_index(self.workspace)
            self.database_path = self.workspace.database_path
            self._validate_database()
            self._refresh_all()
        except (OSError, ValueError, sqlite3.Error) as error:
            messagebox.showerror("Refresh Workspace", str(error), parent=self)
            return
        self.status_var.set(f"Workspace refreshed: {self.workspace.name}")

    def open_workspace_folder(self) -> None:
        try:
            self.workspace.root_path.mkdir(parents=True, exist_ok=True)
            browser.open_with_default_application(str(self.workspace.root_path))
        except OSError as error:
            messagebox.showerror("Open Workspace Folder", str(error), parent=self)

    def update_index(self) -> None:
        self.status_var.set("Updating search index…")
        self.update_idletasks()
        try:
            result = update_archive_index(
                self.workspace.root_path,
                downloads_dir=self.workspace.root_path / "downloads",
                database_path=self.workspace.database_path,
                progress=lambda message: browser.LOGGER.info("Indexer: %s", message),
            )
            self.database_path = self.workspace.database_path
            self._validate_database()
            self._refresh_all()
        except (OSError, ValueError, sqlite3.Error) as error:
            browser.LOGGER.exception("Unable to update workspace index: %s", error)
            self.status_var.set("Index update failed.")
            messagebox.showerror("Update Search Index", str(error), parent=self)
            return
        suffix = f" ({result.failed} source failure(s))" if result.failed else ""
        self.status_var.set(f"Search index updated{suffix}.")

    def _actions(self) -> WorkspaceActions:
        if self.provider_actions is None:
            raise RuntimeError("No provider actions are active for this workspace")
        return self.provider_actions

    def archive_new_conversations(self) -> None:
        self._actions().archive_new()

    def open_provider_service(self) -> None:
        self._actions().open_service()

    def copy_collector_javascript(self) -> None:
        self._actions().copy_collector()

    def show_collector_in_explorer(self) -> None:
        self._actions().show_collector()

    def process_downloaded_export(self) -> None:
        self._actions().process_downloaded()

    def regenerate_missing_docx(self) -> None:
        self._actions().regenerate_missing()

    def show_last_archive_log(self) -> None:
        self._actions().show_last_log()

    def provider_content_changed(self, message: str = "Archive updated.") -> None:
        """Provider callback after collection/archive mutations."""
        try:
            self.update_index()
        except tk.TclError:
            return
        self.status_var.set(message)

    def show_user_guide(self) -> None:
        self._show_markdown_resource(f"{APP_NAME} User Guide", read_user_guide)

    def show_release_history(self) -> None:
        self._show_markdown_resource(f"{APP_NAME} Release History", read_release_history)

    def _show_markdown_resource(self, title: str, reader: Callable[[], str]) -> None:
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


__all__ = [
    "ActionFactory",
    "ConversationWorkspaceApp",
    "WorkspaceActions",
    "ensure_workspace_index",
]
