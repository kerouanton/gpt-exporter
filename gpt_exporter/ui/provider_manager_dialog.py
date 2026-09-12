"""Providers dialog for provider inventory and activation state."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from gpt_exporter.provider_manager import ProviderManager, ProviderRecord, ProviderState
from gpt_exporter.version import APP_NAME


class ProviderManagerDialog(tk.Toplevel):
    """Show provider state and allow durable enable/disable changes."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Providers")
        self.transient(parent)
        self.minsize(780, 380)
        self.manager: ProviderManager | None = None
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
                "Enable/disable changes are persistent and take full effect on the next "
                "application start. Provider packages and archive data are not removed."
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
        self.toggle_button = ttk.Button(
            buttons,
            text="Disable",
            command=self.toggle_selected,
            state="disabled",
        )
        self.toggle_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def refresh(self, *, select_provider_id: str | None = None) -> None:
        self.manager = ProviderManager.discover()
        self._records_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        selected_iid: str | None = None
        for index, record in enumerate(self.manager.records(), start=1):
            iid = f"provider-{index}"
            self._records_by_iid[iid] = record
            if record.provider_id == select_provider_id:
                selected_iid = iid
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
            selected_iid = selected_iid or children[0]
            self.tree.selection_set(selected_iid)
            self.tree.focus(selected_iid)
            self._selection_changed()
        else:
            self.toggle_button.configure(state="disabled")
            self._set_details("No provider was discovered.")

    def _selected_record(self) -> ProviderRecord | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return self._records_by_iid.get(selected[0])

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        record = self._selected_record()
        if record is None:
            self.toggle_button.configure(state="disabled")
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

        if record.state == ProviderState.ENABLED:
            self.toggle_button.configure(text="Disable", state="normal")
        elif record.state == ProviderState.DISABLED:
            self.toggle_button.configure(text="Enable", state="normal")
        else:
            self.toggle_button.configure(text="Enable / Disable", state="disabled")

    def toggle_selected(self) -> None:
        record = self._selected_record()
        if record is None or self.manager is None:
            return
        enabled = record.state == ProviderState.DISABLED
        action = "enable" if enabled else "disable"
        try:
            self.manager.set_enabled(record.provider_id, enabled)
        except (KeyError, OSError, ValueError) as error:
            messagebox.showerror("Providers", str(error), parent=self)
            return

        self.refresh(select_provider_id=record.provider_id)
        messagebox.showinfo(
            "Providers",
            f"{record.display_name} will be {action}d after MSNE is restarted.",
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
