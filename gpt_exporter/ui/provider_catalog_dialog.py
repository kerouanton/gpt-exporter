"""Read-only Stage D provider catalog view."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gpt_exporter.provider_catalog import ProviderCatalog, ProviderCatalogEntry
from gpt_exporter.provider_manager import ProviderManager, ProviderRecord
from gpt_exporter.version import APP_NAME


class ProviderCatalogDialog(tk.Toplevel):
    """Compare a validated catalog snapshot with the current provider inventory."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        catalog: ProviderCatalog,
        manager: ProviderManager,
    ) -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Provider Catalog")
        self.transient(parent)
        self.minsize(920, 460)
        self.catalog = catalog
        self.manager = manager
        self._entries_by_iid: dict[str, ProviderCatalogEntry] = {}
        self._records = {record.provider_id: record for record in manager.records()}

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text=f"Catalog: {catalog.catalog_id}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=f"Generated: {catalog.generated_at} — read-only metadata preview",
        ).pack(anchor="w", pady=(2, 8))

        columns = ("state", "installed", "available", "api", "distribution")
        self.tree = ttk.Treeview(
            outer,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            height=10,
        )
        self.tree.heading("#0", text="Provider")
        self.tree.heading("state", text="Catalog state")
        self.tree.heading("installed", text="Installed")
        self.tree.heading("available", text="Available")
        self.tree.heading("api", text="API")
        self.tree.heading("distribution", text="Distribution")
        self.tree.column("#0", width=170, minwidth=120)
        self.tree.column("state", width=130, minwidth=100)
        self.tree.column("installed", width=90, minwidth=70)
        self.tree.column("available", width=90, minwidth=70)
        self.tree.column("api", width=55, minwidth=45, anchor="center")
        self.tree.column("distribution", width=240, minwidth=160)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.details = tk.Text(outer, height=9, wrap="word", state="disabled")
        self.details.pack(fill="x", pady=(8, 0))
        ttk.Button(outer, text="Close", command=self.destroy).pack(anchor="e", pady=(8, 0))

        for index, entry in enumerate(catalog.entries, start=1):
            iid = f"catalog-{index}"
            self._entries_by_iid[iid] = entry
            record = self._records.get(entry.provider_id)
            installed_version = self._installed_version(record)
            state = self._catalog_state(entry, record)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=entry.display_name,
                values=(
                    state,
                    installed_version or "—",
                    entry.version,
                    str(entry.provider_api_version),
                    entry.distribution_name,
                ),
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._selection_changed()

    @staticmethod
    def _installed_version(record: ProviderRecord | None) -> str:
        if record is None:
            return ""
        return record.managed_version or record.version

    def _catalog_state(
        self,
        entry: ProviderCatalogEntry,
        record: ProviderRecord | None,
    ) -> str:
        if not entry.compatible_provider_api:
            return "Incompatible"
        installed = self._installed_version(record)
        if not installed:
            return "Available"
        try:
            if entry.is_update_for(installed):
                return "Update available"
        except ValueError:
            return "Version unknown"
        return "Installed"

    def _selection_changed(self, _event: tk.Event | None = None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        entry = self._entries_by_iid[selected[0]]
        record = self._records.get(entry.provider_id)
        installed = self._installed_version(record) or "not installed"
        lines = [
            f"Provider ID: {entry.provider_id}",
            f"Distribution: {entry.distribution_name}",
            f"Installed version: {installed}",
            f"Catalog version: {entry.version}",
            f"Provider API: {entry.provider_api_version}",
            f"Minimum MSNE version: {entry.min_msne_version}",
            f"Artifact SHA-256: {entry.sha256}",
            f"Artifact URL: {entry.artifact_url}",
            f"Capabilities: {', '.join(entry.capabilities) or 'none declared'}",
        ]
        if entry.description:
            lines.append(f"Description: {entry.description}")
        lines.append(
            "This Stage D view is read-only. Catalog artifact download/install remains disabled."
        )
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))
        self.details.configure(state="disabled")


def show_provider_catalog(
    parent: tk.Misc,
    *,
    catalog: ProviderCatalog,
    manager: ProviderManager,
) -> ProviderCatalogDialog:
    dialog = ProviderCatalogDialog(parent, catalog=catalog, manager=manager)
    dialog.grab_set()
    return dialog


__all__ = ["ProviderCatalogDialog", "show_provider_catalog"]
