"""Provider-neutral guided archive dialog bound to one workspace."""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from gpt_exporter.acquisition import source_bundle_signature as core_source_bundle_signature
from gpt_exporter.workspaces import Workspace


class WorkspaceArchiveDialog(tk.Toplevel):
    """Guide collection for the currently selected workspace/provider."""

    POLL_MS = 1000

    def __init__(
        self,
        parent: tk.Misc,
        *,
        workspace: Workspace,
        find_source_bundle,
        source_bundle_signature=core_source_bundle_signature,
        on_open_provider,
        on_copy_collector,
        on_run_archive,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.find_source_bundle = find_source_bundle
        self.source_bundle_signature = source_bundle_signature
        self.on_open_provider = on_open_provider
        self.on_copy_collector = on_copy_collector
        self.on_run_archive = on_run_archive

        provider = workspace.provider
        self.title("Archive New Conversations")
        self.geometry("760x360")
        self.minsize(640, 280)
        self.resizable(True, True)
        self.transient(parent)

        self.collector_var = tk.StringVar(value="Preparing collector JavaScript…")
        self.bundle_var = tk.StringVar(
            value=f"Waiting for a new {provider.source_bundle_name} in Downloads…"
        )
        self._poll_after_id: str | None = None
        self._archive_started = False
        self._initial_bundle_signature = self.source_bundle_signature(
            self.find_source_bundle()
        )

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Archive New Conversations",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._step(
            body,
            f"1. Open {provider.display_name}",
            f"Open {provider.display_name} in your normal browser and make sure you are signed in.",
        )
        ttk.Button(
            body,
            text=f"Open {provider.display_name}",
            command=self.on_open_provider,
        ).pack(anchor="w", pady=(0, 10))

        self._step(
            body,
            "2. Run the collector",
            "The collector JavaScript is copied to the clipboard automatically. "
            "Open Developer Tools (F12), select Console, paste it and run it.",
        )
        collector_row = ttk.Frame(body)
        collector_row.pack(fill="x", pady=(0, 10))
        ttk.Label(collector_row, textvariable=self.collector_var).pack(side="left")
        ttk.Button(
            collector_row,
            text="Copy Again",
            command=self._copy_collector,
        ).pack(side="right")

        self._step(
            body,
            "3. Wait for the browser download",
            f"When the collector finishes, the browser downloads {provider.source_bundle_name}. "
            "As soon as a new non-empty bundle is detected, the archive workflow starts automatically.",
        )
        ttk.Label(body, textvariable=self.bundle_var, wraplength=700).pack(
            anchor="w", fill="x", pady=(0, 10)
        )

        action_row = ttk.Frame(body)
        action_row.pack(fill="x", pady=(2, 0))
        ttk.Button(action_row, text="Close", command=self.destroy).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after_idle(self._copy_collector)
        self._check_bundle()

    @staticmethod
    def _step(parent: ttk.Frame, title: str, text: str) -> None:
        ttk.Label(parent, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(parent, text=text, wraplength=700, justify="left").pack(
            anchor="w", fill="x", pady=(2, 5)
        )

    def _copy_collector(self) -> None:
        copied = bool(self.on_copy_collector())
        if copied:
            self.collector_var.set("Collector JavaScript copied to the clipboard.")
        else:
            self.collector_var.set("Collector JavaScript could not be copied automatically.")

    def _check_bundle(self) -> None:
        if self._archive_started:
            return
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None

        provider = self.workspace.provider
        bundle = self.find_source_bundle()
        signature = self.source_bundle_signature(bundle)
        if bundle is None:
            self.bundle_var.set(
                f"Waiting for a new {provider.source_bundle_name} in Downloads…"
            )
        elif signature == self._initial_bundle_signature:
            self.bundle_var.set(
                "An existing bundle is present; waiting for a new browser download…"
            )
        else:
            self._archive_started = True
            self.bundle_var.set(f"Detected: {bundle}. Starting archive workflow…")
            self.after(150, self._run_archive)
            return

        if self.winfo_exists():
            self._poll_after_id = self.after(self.POLL_MS, self._check_bundle)

    def _run_archive(self) -> None:
        bundle = self.find_source_bundle()
        if bundle is None:
            self._archive_started = False
            self.bundle_var.set("The detected bundle is no longer available; waiting again…")
            self._poll_after_id = self.after(self.POLL_MS, self._check_bundle)
            return

        started = bool(self.on_run_archive())
        if started:
            self.destroy()
            return

        self._archive_started = False
        self._initial_bundle_signature = self.source_bundle_signature(bundle)
        self.bundle_var.set("Archive workflow did not start; waiting for another new bundle…")
        self._poll_after_id = self.after(self.POLL_MS, self._check_bundle)


__all__ = ["WorkspaceArchiveDialog"]
