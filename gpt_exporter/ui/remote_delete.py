"""Provider-neutral safety workflow for destructive remote conversation actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
import tkinter as tk
from tkinter import messagebox, ttk


@dataclass(frozen=True, slots=True)
class RemoteDeletionPlan:
    provider_id: str
    conversation_id: str
    conversation_title: str
    operation_label: str
    remote_candidate_ids: tuple[str, ...]
    archived_candidate_ids: tuple[str, ...]
    missing_candidate_ids: tuple[str, ...]
    dry_run_path: Path
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def safe_to_execute(self) -> bool:
        return bool(self.remote_candidate_ids) and not self.missing_candidate_ids


class RemoteDeletionActions(Protocol):
    service_label: str
    remote_delete_label: str

    def open_service(self) -> None: ...
    def snapshot_remote_delete_dry_runs(self): ...
    def copy_remote_delete_dry_run(self, row: dict[str, Any]) -> bool: ...
    def find_remote_delete_dry_run(self, snapshot, row: dict[str, Any]) -> Path | None: ...
    def prepare_remote_deletion(
        self, row: dict[str, Any], dry_run_path: Path
    ) -> RemoteDeletionPlan: ...
    def copy_remote_delete_execute(self, plan: RemoteDeletionPlan) -> bool: ...


class RemoteDeletionDialog(tk.Toplevel):
    """Common dry-run -> local archive verification -> explicit confirmation UI."""

    POLL_MS = 1000

    def __init__(
        self,
        parent: tk.Misc,
        *,
        row: dict[str, Any],
        actions: RemoteDeletionActions,
    ) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.row = dict(row)
        self.actions = actions
        self.snapshot = None
        self.plan: RemoteDeletionPlan | None = None
        self.after_id: str | None = None

        title = str(row.get("title") or "Conversation")
        self.title(f"Remote Deletion — {title}")
        self.geometry("780x500")
        self.minsize(680, 430)
        self.transient(parent)

        self.status_var = tk.StringVar(value="Preparing dry run…")
        self.summary_var = tk.StringVar(value="No dry-run result yet.")

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=f"Remote cleanup: {title}",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._step(
            body,
            "1. Open the archived conversation on the service",
            f"Open the same conversation in {actions.service_label}. The local archive is never deleted by this workflow.",
        )
        ttk.Button(body, text=f"Open {actions.service_label}", command=actions.open_service).pack(
            anchor="w", pady=(0, 10)
        )

        self._step(
            body,
            "2. Run a dry run",
            "A read-only collector is copied to the clipboard. Run it in the browser DevTools console. "
            "The downloaded result is compared against the already archived local conversation.",
        )
        dry_row = ttk.Frame(body)
        dry_row.pack(fill="x", pady=(0, 10))
        ttk.Label(dry_row, textvariable=self.status_var, wraplength=590).pack(side="left", fill="x", expand=True)
        ttk.Button(dry_row, text="Copy Dry Run Again", command=self._copy_dry_run).pack(side="right")

        self._step(
            body,
            "3. Verify archive coverage",
            "Deletion is enabled only when every remote deletion candidate is already present in the local canonical archive.",
        )
        ttk.Label(body, textvariable=self.summary_var, justify="left", wraplength=730).pack(
            anchor="w", fill="x", pady=(0, 12)
        )

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.confirm_button = ttk.Button(
            buttons,
            text="Confirm Remote Deletion…",
            command=self._confirm,
            state="disabled",
        )
        self.confirm_button.pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Destroy>", self._destroyed, add="+")
        self.after_idle(self._arm)

    @staticmethod
    def _step(parent: ttk.Frame, title: str, text: str) -> None:
        ttk.Label(parent, text=title, font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
        ttk.Label(parent, text=text, wraplength=730, justify="left").pack(
            anchor="w", fill="x", pady=(2, 6)
        )

    def _arm(self) -> None:
        try:
            self.snapshot = self.actions.snapshot_remote_delete_dry_runs()
        except Exception as error:
            self.status_var.set(f"Could not arm dry run: {error}")
            return
        self._copy_dry_run()
        self._poll()

    def _copy_dry_run(self) -> None:
        try:
            copied = bool(self.actions.copy_remote_delete_dry_run(self.row))
        except Exception as error:
            copied = False
            self.status_var.set(f"Could not copy dry-run collector: {error}")
        if copied:
            self.status_var.set("Dry-run collector copied. Run it in the selected conversation's DevTools console…")

    def _poll(self) -> None:
        try:
            path = self.actions.find_remote_delete_dry_run(self.snapshot, self.row)
        except Exception as error:
            self.status_var.set(f"Dry-run validation failed: {error}")
            path = None
        if path is not None:
            self._accept_dry_run(path)
            return
        self.after_id = self.after(self.POLL_MS, self._poll)

    def _accept_dry_run(self, path: Path) -> None:
        try:
            plan = self.actions.prepare_remote_deletion(self.row, Path(path))
        except Exception as error:
            self.status_var.set(f"Dry-run result rejected: {error}")
            self.after_id = self.after(self.POLL_MS, self._poll)
            return

        self.plan = plan
        remote = len(plan.remote_candidate_ids)
        archived = len(plan.archived_candidate_ids)
        missing = len(plan.missing_candidate_ids)
        self.status_var.set(f"Dry run validated: {Path(path).name}")
        self.summary_var.set(
            f"Remote deletion candidates: {remote}\n"
            f"Already archived locally: {archived}\n"
            f"Not found in local archive: {missing}\n\n"
            + (
                "Safe to continue. The local archive will be preserved."
                if plan.safe_to_execute
                else (
                    "Deletion is blocked because some remote candidates are not archived locally. "
                    "Archive the conversation again first."
                    if missing
                    else "No deletable messages were found."
                )
            )
        )
        self.confirm_button.configure(state="normal" if plan.safe_to_execute else "disabled")

    def _confirm(self) -> None:
        plan = self.plan
        if plan is None or not plan.safe_to_execute:
            return
        count = len(plan.remote_candidate_ids)
        if not messagebox.askyesno(
            "Confirm Remote Deletion",
            f"Delete {count} remote message(s) from {plan.conversation_title}?\n\n"
            "Every deletion candidate was verified as already archived locally.\n"
            "The local archive and DOCX will not be deleted.\n\n"
            "Continue?",
            parent=self,
            icon="warning",
        ):
            return
        try:
            copied = bool(self.actions.copy_remote_delete_execute(plan))
        except Exception as error:
            messagebox.showerror("Remote Deletion", str(error), parent=self)
            return
        if not copied:
            return
        self.confirm_button.configure(state="disabled")
        self.status_var.set(
            "Deletion payload copied. Paste and run it in the SAME conversation's DevTools console."
        )
        self.summary_var.set(
            f"Authorized candidates: {count}\n\n"
            "The destructive payload is pinned to this archived conversation and this exact dry-run candidate set. "
            "It will refuse to run in another conversation."
        )

    def _destroyed(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None


__all__ = ["RemoteDeletionActions", "RemoteDeletionDialog", "RemoteDeletionPlan"]
