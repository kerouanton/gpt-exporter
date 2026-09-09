"""Provider-neutral UI for browser-collector archive workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ArchiveWorkflowSpec:
    """Provider-supplied copy for the shared archive workflow dialog."""

    service_label: str
    open_instructions: str
    collector_instructions: str
    download_instructions: str
    waiting_text: str


class ArchiveWorkflowActions(Protocol):
    """Provider capabilities consumed by :class:`ArchiveWorkflowDialog`."""

    archive_workflow_spec: ArchiveWorkflowSpec

    def open_service(self) -> None: ...
    def copy_collector(self) -> bool: ...
    def snapshot_exports(self) -> Any: ...
    def find_new_export(self, snapshot: Any) -> Path | None: ...
    def process_export(self, path: Path) -> bool: ...


class ArchiveWorkflowDialog(tk.Toplevel):
    """Guide collection and automatically process the next browser export."""

    POLL_MS = 1000

    def __init__(self, parent: tk.Misc, *, actions: ArchiveWorkflowActions) -> None:
        super().__init__(parent)
        self.title("Archive New Conversations")
        self.geometry("760x360")
        self.minsize(640, 280)
        self.resizable(True, True)
        self.transient(parent)

        self.actions = actions
        self.spec = actions.archive_workflow_spec
        self.collector_var = tk.StringVar(value="Preparing collector JavaScript…")
        self.export_var = tk.StringVar(value=self.spec.waiting_text)
        self._poll_after_id: str | None = None
        self._archive_started = False

        try:
            self._initial_snapshot = actions.snapshot_exports()
        except Exception as error:
            self._initial_snapshot = None
            self.export_var.set(f"Could not inspect Downloads: {error}")

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Archive New Conversations",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._step(
            body,
            f"1. Open {self.spec.service_label}",
            self.spec.open_instructions,
        )
        ttk.Button(
            body,
            text=f"Open {self.spec.service_label}",
            command=self.actions.open_service,
        ).pack(anchor="w", pady=(0, 10))

        self._step(body, "2. Run the collector", self.spec.collector_instructions)
        collector_row = ttk.Frame(body)
        collector_row.pack(fill="x", pady=(0, 10))
        ttk.Label(collector_row, textvariable=self.collector_var).pack(side="left")
        ttk.Button(
            collector_row,
            text="Copy Again",
            command=self._copy_collector,
        ).pack(side="right")

        self._step(body, "3. Wait for the browser download", self.spec.download_instructions)
        ttk.Label(body, textvariable=self.export_var, wraplength=700).pack(
            anchor="w", fill="x", pady=(0, 10)
        )

        action_row = ttk.Frame(body)
        action_row.pack(fill="x", pady=(2, 0))
        ttk.Button(action_row, text="Close", command=self.destroy).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after_idle(self._copy_collector)
        self._check_export()

    @staticmethod
    def _step(parent: ttk.Frame, title: str, text: str) -> None:
        ttk.Label(parent, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(parent, text=text, wraplength=700, justify="left").pack(
            anchor="w", fill="x", pady=(2, 5)
        )

    def _copy_collector(self) -> None:
        copied = bool(self.actions.copy_collector())
        if copied:
            self.collector_var.set("Collector JavaScript copied to the clipboard.")
        else:
            self.collector_var.set("Collector JavaScript could not be copied automatically.")

    def _check_export(self) -> None:
        if self._archive_started:
            return

        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None

        try:
            export_path = self.actions.find_new_export(self._initial_snapshot)
        except Exception as error:
            self.export_var.set(f"Waiting for a valid browser export… ({error})")
            export_path = None

        if export_path is not None:
            self._archive_started = True
            self.export_var.set(f"Detected: {export_path}. Starting archive workflow…")
            self.after(150, lambda path=Path(export_path): self._run_archive(path))
            return

        if self.winfo_exists():
            self._poll_after_id = self.after(self.POLL_MS, self._check_export)

    def _run_archive(self, path: Path) -> None:
        started = bool(self.actions.process_export(path))
        if started:
            self.destroy()
            return

        self._archive_started = False
        try:
            self._initial_snapshot = self.actions.snapshot_exports()
        except Exception:
            pass
        self.export_var.set("Archive workflow did not start; waiting for another new export…")
        self._poll_after_id = self.after(self.POLL_MS, self._check_export)


__all__ = ["ArchiveWorkflowActions", "ArchiveWorkflowDialog", "ArchiveWorkflowSpec"]
