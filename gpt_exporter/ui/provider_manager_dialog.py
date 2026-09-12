"""Providers dialog for ProviderManager lifecycle and managed artifact operations."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gpt_exporter.provider_artifacts import ProviderArtifactStore, inspect_provider_wheel
from gpt_exporter.provider_manager import ProviderManager, ProviderRecord, ProviderState
from gpt_exporter.provider_runtime import (
    install_provider_with_validation,
    validate_provider_dependency_policy,
)
from gpt_exporter.version import APP_NAME


class ProviderManagerDialog(tk.Toplevel):
    """Show discovered providers and manage activation/local wheel artifacts."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title(f"{APP_NAME} — Providers")
        self.transient(parent)
        self.minsize(900, 440)
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
                "Enable/disable changes are persistent. Managed provider wheels are isolated "
                "in the per-user MSNE provider directory."
            ),
        ).pack(anchor="w", pady=(2, 8))

        columns = ("status", "version", "source", "api", "capabilities")
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
        self.tree.heading("source", text="Source")
        self.tree.heading("api", text="API")
        self.tree.heading("capabilities", text="Capabilities")
        self.tree.column("#0", width=170, minwidth=120)
        self.tree.column("status", width=100, minwidth=80)
        self.tree.column("version", width=80, minwidth=60)
        self.tree.column("source", width=135, minwidth=110)
        self.tree.column("api", width=60, minwidth=50, anchor="center")
        self.tree.column("capabilities", width=300, minwidth=180)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.details = tk.Text(outer, height=8, wrap="word", state="disabled")
        self.details.pack(fill="x", pady=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(8, 0))
        self.install_button = ttk.Button(
            buttons,
            text="Install / Update from file...",
            command=self._install_from_file,
        )
        self.install_button.pack(side="left")
        self.remove_button = ttk.Button(
            buttons,
            text="Remove managed copy",
            command=self._remove_selected,
        )
        self.remove_button.pack(side="left", padx=(6, 0))
        self.enable_button = ttk.Button(buttons, text="Enable", command=self._enable_selected)
        self.enable_button.pack(side="left", padx=(12, 0))
        self.disable_button = ttk.Button(buttons, text="Disable", command=self._disable_selected)
        self.disable_button.pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Refresh", command=self.refresh).pack(side="left", padx=(12, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def refresh(self) -> None:
        self.manager = ProviderManager.discover(artifact_root=self.artifact_store.root)
        self._records_by_iid.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        for index, record in enumerate(self.manager.records(), start=1):
            iid = f"provider-{index}"
            self._records_by_iid[iid] = record
            capabilities = ", ".join(record.capabilities) or "—"
            api = str(record.api_version) if record.api_version is not None else "—"
            version = record.version or record.managed_version or "—"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=record.display_name,
                values=(record.status_label, version, record.provenance_label, api, capabilities),
            )

        children = self.tree.get_children()
        if children:
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])
            self._selection_changed()
        else:
            self._set_details(
                "No provider was discovered. Use Install / Update from file... to install a provider wheel."
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
            f"Loaded successfully: {'yes' if record.discovered else 'no'}",
            f"Source: {record.provenance_label}",
            f"Managed provider directory: {self.artifact_store.root}",
        ]
        if record.managed:
            lines.extend(
                [
                    f"Managed distribution: {record.managed_distribution}",
                    f"Managed version: {record.managed_version or 'unknown'}",
                    f"Artifact SHA-256: {record.managed_sha256 or 'unknown (installed before provenance tracking)'}",
                    f"Source artifact: {record.managed_source_filename or 'unknown'}",
                    f"Installed at: {record.managed_installed_at or 'unknown'}",
                ]
            )
        if record.entry_point:
            lines.append(f"Entry point: {record.entry_point}")
        if record.error:
            lines.append(f"Error: {record.error}")
        self._set_details("\n".join(lines))
        self._update_buttons(record)

    def _update_buttons(self, record: ProviderRecord | None) -> None:
        can_enable = record is not None and record.state == ProviderState.DISABLED
        can_disable = record is not None and record.state == ProviderState.ENABLED
        can_remove = record is not None and record.managed
        self.enable_button.configure(state="normal" if can_enable else "disabled")
        self.disable_button.configure(state="normal" if can_disable else "disabled")
        self.remove_button.configure(state="normal" if can_remove else "disabled")

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
            title="Install or Update Provider",
            filetypes=(("Python wheel", "*.whl"), ("All files", "*.*")),
        )
        if not filename:
            return
        try:
            artifact = inspect_provider_wheel(filename)
            requirements = validate_provider_dependency_policy(artifact.path)
            destination = self.artifact_store.destination_for(artifact)
            existing = self.artifact_store.managed_for_distribution(
                artifact.distribution_name
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return

        action = "Update" if existing is not None else "Install"
        entry_points = "\n".join(
            f"  {name} = {value}" for name, value in artifact.entry_points
        )
        current = ""
        if existing is not None:
            current = (
                f"Current managed version: {existing.version}\n"
                f"Current SHA-256: {existing.sha256 or 'unknown'}\n"
            )
        dependency_text = "\n".join(f"  {item}" for item in requirements) or "  none"
        prompt = (
            f"{action} provider distribution?\n\n"
            f"Distribution: {artifact.distribution_name}\n"
            f"Version: {artifact.version}\n"
            f"SHA-256: {artifact.sha256}\n"
            f"{current}"
            f"Entry points:\n{entry_points}\n"
            f"Runtime requirements:\n{dependency_text}\n\n"
            f"Destination:\n{destination}\n\n"
            "MSNE will install the wheel, load its provider entry points, verify the provider "
            "API, and automatically restore the previous managed version if validation fails.\n\n"
            "Installing a provider installs executable Python code. Continue?"
        )
        if not messagebox.askyesno(APP_NAME, prompt, parent=self):
            return

        try:
            installed, provider_ids = install_provider_with_validation(
                self.artifact_store,
                artifact,
            )
        except (OSError, TypeError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return

        self.refresh()
        validated_ids = ", ".join(provider_ids)
        messagebox.showinfo(
            APP_NAME,
            (
                f"{action}d {installed.distribution_name} {installed.version}.\n"
                f"Validated provider ID(s): {validated_ids}.\n\n"
                "The provider inventory has been refreshed. Restart MSNE before using "
                "a newly installed or replaced provider in an active workspace."
            ),
            parent=self,
        )

    def _remove_selected(self) -> None:
        record = self._selected_record()
        if record is None or not record.managed:
            return
        prompt = (
            "Remove the locally managed provider copy?\n\n"
            f"Provider: {record.display_name} ({record.provider_id})\n"
            f"Distribution: {record.managed_distribution}\n"
            f"Version: {record.managed_version or 'unknown'}\n"
            f"SHA-256: {record.managed_sha256 or 'unknown'}\n\n"
            "This removes only the MSNE-managed copy. A bundled, editable or globally "
            "installed copy may still be discovered after restart. Archive data is not removed."
        )
        if not messagebox.askyesno(APP_NAME, prompt, parent=self):
            return
        try:
            removed = self.artifact_store.remove_distribution(
                record.managed_distribution
            )
        except (OSError, ValueError) as error:
            messagebox.showerror(APP_NAME, str(error), parent=self)
            return

        self.refresh()
        messagebox.showinfo(
            APP_NAME,
            (
                f"Removed managed distribution {removed.distribution_name} {removed.version}.\n\n"
                "Restart MSNE to rebuild provider discovery without that managed copy."
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
