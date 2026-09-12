"""Read-only Providers dialog for the first ProviderManager UI stage."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gpt_exporter.provider_manager import ProviderManager, ProviderRecord
from gpt_exporter.version import APP_NAME


class ProviderManagerDialog(tk.Toplevel):
    """Show discovered, incompatible and broken provider candidates."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Providers")
        self.transient(parent)
        self.minsize(760, 360)
        self.manager = ProviderManager.discover()
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
                "Read-only inventory. Install, update, enable/disable and remove "
                "operations will be added in the next ProviderManager stage."
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

        self.details = tk.Text(outer, height=5, wrap="word", state="disabled")
        self.details.pack(fill="x", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left")
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
            self._set_details("No provider was discovered.")

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        record = self._records_by_iid.get(selected[0])
        if record is None:
            return

        lines = [
            f"ID: {record.provider_id}",
            f"Status: {record.status_label}",
            f"Installed candidate: {'yes' if record.installed else 'no'}",
            f"Loaded successfully: {'yes' if record.discovered else 'no'}",
        ]
        if record.entry_point:
            lines.append(f"Entry point: {record.entry_point}")
        if record.error:
            lines.append(f"Error: {record.error}")
        self._set_details("\n".join(lines))

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
