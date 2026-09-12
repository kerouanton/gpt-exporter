"""Providers dialog for ProviderManager lifecycle and local artifact installation."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gpt_exporter.provider_artifacts import ProviderArtifactStore, inspect_provider_wheel
from gpt_exporter.provider_manager import ProviderManager, ProviderRecord, ProviderState
from gpt_exporter.version import APP_NAME


class ProviderManagerDialog(tk.Toplevel):
    """Show discovered providers and manage activation/local wheel installation."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Providers")
        self.transient(parent)
        self.minsize(800, 410)
        self.manager: ProviderManager | None = None
        self.artifact_store = ProviderArtifactStore()
        self._records_by_iid: dict[str, ProviderRecord] = {}

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Installed / discovered providers",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Enable/disable changes are persistent. Provider wheels installed here "
                "are isolated in the per-user MSNE provider directory."
            ),
        ).pack(anchor="w", pady=(2, 8))

        columns = ("status", "version", "api", "capabilities")
        self.tree = ttk.Treeview(
            outer,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            height=9,
        )
        self.tree.heading("#0", text="Provider")
        self.tree.heading("status", text="Status")
        self.tree.heading("version", text="Version")
        self.tree.heading("api", text="API")
        self.tree.heading("capabilities", text="Capabilities")
        self.tree.column("#0", width=170, minwidth=120)
        self.tree.column("status", width=100, minwidth=80)
        self.tree.column("version", width=80, minwidth=60)
        self.tree.column("api", width=60, minwidth=50, anchor="center")
        self.tree.column("capabilities", width=320, minwidth=180)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.details = tk.Text(outer, height=6, wrap="word", state="disabled")
        self.details.pack(fill="x", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        self.install_button = ttk.Button(
            buttons,
            text="Install from file...",
            command=self._install_from_file,
        )
        self.install_button.pack(side="left")
        self.enable_button = ttk.Button(buttons, text="Enable", command=self._enable_selected)
        self.enable_button.pack(side="left", padx=(12, 0))
        self.disable_button = ttk.Button(buttons, text="Disable", command=self._disable_selected)
        self.disable_button.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left", padx=(12, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def refresh(self) -> None:
        self.manager = ProviderManager.discover()
        self._records_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        for index, record in enumerate(self.manager.records(), start=1):
            iid = f"provider-{index}"
            self._records_by_iid[iid] = record
            capabilities = ", ".join(record.capabilities) or "—"
            api = str(record.api_version) if record.api_version is not None else "—"
            version = record.version or "—"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=record.display_name,
                values=(record.status_label, version, api, capabilities),
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._selection_changed()
        else:
            self._set_details(
                "No provider was discovered. Use Install from file... to install a provider wheel."
            )
            self._update_buttons(None)

    def _selected_record(self) -> ProviderRecord | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return self._records_by_iid.get(selected[0])

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        record = self._selected_record()
        if record is None:
            self._update_buttons(None)
            return

        lines = [
            f"ID: {record.provider_id}",
            f"Status: {record.status_label}",
            f"Installed candidate: {'yes' if record.installed else 'no'}",
            f"Loaded successfully: {'yes' if record.discovered else 'no'}",
            f"Managed provider directory: {self.artifact_store.root}",
        ]
        if record.entry_point:
            lines.append(f"Entry point: {record.entry_point}")
        if record.error:
            lines.append(f"Error: {record.error}")
        self._set_details("\n".join(lines))
        self._update_buttons(record)

    def _update_buttons(self, record: ProviderRecord | None) -> None:
        can_enable = record is not None and record.state == ProviderState.DISABLED
        can_disable = record is not None and record.state == ProviderState.ENABLED
        self.enable_button.configure(state="normal" if can_enable else "disabled")
        self.disable_button.configure(state="normal" if can_disable else "disabled")

    def _set_provider_enabled(self, enabled: bool) -> None:
        record = self._selected_record()
        if record is None or self.manager is None:
            return
        try:
            self.manager.set_enabled(record.provider_id, enabled)
        except (KeyError, OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return
        self.refresh()

    def _enable_selected(self) -> None:
        self._set_provider_enabled(True)

    def _disable_selected(self) -> None:
        self._set_provider_enabled(False)

    def _install_from_file(self) -> None:
        filename = filedialog.askopenfilename(
            parent=self,
            title="Install Provider",
            filetypes=(("Python wheel", "*.whl"), ("All files", "*.*")),
        )
        if not filename:
            return
        try:
            artifact = inspect_provider_wheel(filename)
        except (FileNotFoundError, OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return

        entry_points = "\n".join(
            f"  {name} = {value}" for name, value in artifact.entry_points
        )
        destination = self.artifact_store.destination_for(artifact)
        prompt = (
            f"Install provider distribution?\n\n"
            f"Distribution: {artifact.distribution_name}\n"
            f"Version: {artifact.version}\n"
            f"SHA-256: {artifact.sha256}\n"
            f"Entry points:\n{entry_points}\n\n"
            f"Destination:\n{destination}\n\n"
            "Installing a provider installs executable Python code. Continue?"
        )
        if not messagebox.askyesno(APP_NAME, prompt, parent=self):
            return

        try:
            installed = self.artifact_store.install(artifact.path)
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return

        self.refresh()
        messagebox.showinfo(
            APP_NAME,
            (
                f"Installed {installed.distribution_name} {installed.version}.\n\n"
                "The provider inventory has been refreshed. Restart MSNE before using "
                "a newly installed or replaced provider in an active workspace."
            ),
            parent=self,
        )

    def _set_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")


def show_provider_manager(parent: tk.Misc) -> ProviderManagerDialog:
    dialog = ProviderManagerDialog(parent)
    dialog.grab_set()
    return dialog


__all__ = ["ProviderManagerDialog", "show_provider_manager"]
