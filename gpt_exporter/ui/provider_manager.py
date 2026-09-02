"""Core GUI for inspecting installed exporter providers."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gpt_exporter.providers import ProviderRegistry


class ProviderManagerDialog(tk.Toplevel):
    """Display providers known to the exporter core."""

    def __init__(self, parent: tk.Misc, registry: ProviderRegistry) -> None:
        super().__init__(parent)
        self.title("Manage Providers")
        self.geometry("760x420")
        self.minsize(620, 340)
        self.transient(parent)

        self.registry = registry

        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Installed Providers",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        columns = ("name", "key", "archive", "collector", "website")
        self.tree = ttk.Treeview(outer, columns=columns, show="headings", selectmode="browse")
        headings = {
            "name": "Name",
            "key": "Provider ID",
            "archive": "Default Archive",
            "collector": "Collector",
            "website": "Website",
        }
        widths = {
            "name": 120,
            "key": 100,
            "archive": 170,
            "collector": 190,
            "website": 170,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=80, anchor="w")

        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="left", fill="y")

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self._populate()
        self.bind("<Escape>", lambda _event: self.destroy())

    def _populate(self) -> None:
        for provider in self.registry.all():
            self.tree.insert(
                "",
                "end",
                iid=provider.key,
                values=(
                    provider.display_name,
                    provider.key,
                    provider.archive_directory_name,
                    provider.collector_name,
                    provider.website_url,
                ),
            )


def show_provider_manager(parent: tk.Misc, registry: ProviderRegistry) -> ProviderManagerDialog:
    """Open the provider manager dialog."""
    return ProviderManagerDialog(parent, registry)


__all__ = ["ProviderManagerDialog", "show_provider_manager"]
