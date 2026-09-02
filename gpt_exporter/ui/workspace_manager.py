"""Workspace management UI for exporter-core."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from gpt_exporter.index import initialize_normalized_database
from gpt_exporter.providers import ProviderRegistry
from gpt_exporter.workspaces import Workspace, WorkspaceRegistry, save_workspace_registry


class WorkspaceManagerDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        workspaces: WorkspaceRegistry,
        providers: ProviderRegistry,
        on_changed=None,
    ) -> None:
        super().__init__(parent)
        self.workspaces = workspaces
        self.providers = providers
        self.on_changed = on_changed
        self.title("Manage Workspaces")
        self.geometry("860x360")
        self.minsize(700, 300)
        self.transient(parent)

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            body,
            columns=("provider", "archive"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Workspace")
        self.tree.heading("provider", text="Provider")
        self.tree.heading("archive", text="Archive Root")
        self.tree.column("#0", width=190)
        self.tree.column("provider", width=140)
        self.tree.column("archive", width=470)
        self.tree.pack(fill="both", expand=True)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Add…", command=self._add).pack(side="left")
        ttk.Button(buttons, text="Edit…", command=self._edit).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Remove", command=self._remove).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._refresh()

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for workspace in self.workspaces.all():
            self.tree.insert(
                "",
                "end",
                iid=workspace.key,
                text=workspace.display_name,
                values=(workspace.provider.display_name, str(workspace.archive_root)),
            )

    def _selected(self) -> Workspace | None:
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return self.workspaces.get(selection[0])
        except KeyError:
            return None

    def _choose_provider(self, initial: str | None = None):
        providers = self.providers.all()
        if not providers:
            messagebox.showerror("Manage Workspaces", "No providers are installed.", parent=self)
            return None
        names = [provider.display_name for provider in providers]
        prompt = "Provider:\n\n" + "\n".join(f"- {name}" for name in names)
        value = simpledialog.askstring(
            "Workspace Provider",
            prompt,
            initialvalue=initial or names[0],
            parent=self,
        )
        if value is None:
            return None
        for provider in providers:
            if provider.display_name.casefold() == value.strip().casefold() or provider.key.casefold() == value.strip().casefold():
                return provider
        messagebox.showerror("Workspace Provider", f"Unknown provider: {value}", parent=self)
        return None

    def _workspace_values(self, existing: Workspace | None = None):
        name = simpledialog.askstring(
            "Workspace Name",
            "Workspace name:",
            initialvalue=existing.display_name if existing else "",
            parent=self,
        )
        if name is None or not name.strip():
            return None
        provider = self._choose_provider(existing.provider.display_name if existing else None)
        if provider is None:
            return None
        initial_dir = str(existing.archive_root if existing else Path.home() / "Documents")
        archive = filedialog.askdirectory(
            title="Select Workspace Archive Root",
            initialdir=initial_dir,
            parent=self,
        )
        if not archive:
            return None
        key = existing.key if existing else self._unique_key(name)
        return Workspace(
            key=key,
            display_name=name.strip(),
            provider=provider,
            archive_root=Path(archive),
        )

    def _unique_key(self, name: str) -> str:
        base = "-".join(part for part in name.strip().casefold().replace("_", "-").split() if part) or "workspace"
        key = base
        suffix = 2
        existing = {workspace.key.casefold() for workspace in self.workspaces.all()}
        while key.casefold() in existing:
            key = f"{base}-{suffix}"
            suffix += 1
        return key

    def _prepare_workspace(self, workspace: Workspace) -> bool:
        try:
            initialize_normalized_database(workspace.database_path)
        except (OSError, ValueError) as error:
            messagebox.showerror(
                "Manage Workspaces",
                f"The workspace archive could not be initialized:\n\n{workspace.archive_root}\n\n{error}",
                parent=self,
            )
            return False
        return True

    def _persist(self) -> None:
        save_workspace_registry(self.workspaces)
        self._refresh()
        if self.on_changed is not None:
            self.on_changed()

    def _add(self) -> None:
        workspace = self._workspace_values()
        if workspace is None or not self._prepare_workspace(workspace):
            return
        self.workspaces.register(workspace)
        self._persist()
        self.tree.selection_set(workspace.key)

    def _edit(self) -> None:
        existing = self._selected()
        if existing is None:
            return
        workspace = self._workspace_values(existing)
        if workspace is None or not self._prepare_workspace(workspace):
            return
        self.workspaces.replace(workspace)
        self._persist()
        self.tree.selection_set(workspace.key)

    def _remove(self) -> None:
        existing = self._selected()
        if existing is None:
            return
        if len(self.workspaces) <= 1:
            messagebox.showwarning("Manage Workspaces", "At least one workspace must remain.", parent=self)
            return
        if not messagebox.askyesno(
            "Remove Workspace",
            f"Remove workspace '{existing.display_name}'?\n\nNo archive files will be deleted.",
            parent=self,
        ):
            return
        self.workspaces.remove(existing.key)
        self._persist()


def show_workspace_manager(
    parent: tk.Misc,
    *,
    workspaces: WorkspaceRegistry,
    providers: ProviderRegistry,
    on_changed=None,
) -> WorkspaceManagerDialog:
    return WorkspaceManagerDialog(
        parent,
        workspaces=workspaces,
        providers=providers,
        on_changed=on_changed,
    )


__all__ = ["WorkspaceManagerDialog", "show_workspace_manager"]
