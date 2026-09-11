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

    def open_service(self, row: dict[str, Any] | None = None) -> None: ...
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
        self.deletion_confirmed = False

        title = str(row.get("title") or "Conversation")
        self.title(f"Remote Deletion — {title}")
        self.geometry("780x590")
        self.minsize(680, 500)
        self.transient(parent)

        self.status_var = tk.StringVar(value="Preparing dry run…")
        self.summary_var = tk.StringVar(value="No dry-run result yet.")
        self.delete_status_var = tk.StringVar(
            value="Deletion script is locked until archive coverage is verified."
        )

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
        ttk.Button(
            body,
            text=f"Open {actions.service_label}",
            command=lambda: actions.open_service(self.row),
        ).pack(anchor="w", pady=(0, 10))

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

        self._step(
            body,
            "4. Confirm Remote Deletion",
            "The deletion script is available only after archive coverage is complete. "
            "It is pinned to this conversation, the current account, and the exact dry-run candidate set.",
        )
        delete_row = ttk.Frame(body)
        delete_row.pack(fill="x", pady=(0, 10))
        ttk.Label(delete_row, textvariable=self.delete_status_var, wraplength=560).pack(
            side="left", fill="x", expand=True
        )
        self.confirm_button = ttk.Button(
            delete_row,
            text="Copy Deletion Script",
            command=self._confirm,
            state="disabled",
        )
        self.confirm_button.pack(side="right")

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

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
        self.deletion_confirmed = False
        remote = len(plan.remote_candidate_ids)
        archived = len(plan.archived_candidate_ids)
        missing = len(plan.missing_candidate_ids)
        self.status_var.set(f"Dry run validated: {Path(path).name}")
        self.summary_var.set(
            f"Remote candidates:        {remote}\n"
            f"Archived locally:         {archived}\n"
            f"Not archived locally:     {missing}\n"
            f"Status: {'SAFE' if plan.safe_to_execute else 'BLOCKED'}\n\n"
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
        if plan.safe_to_execute:
            self.delete_status_var.set(
                f"Ready to copy the deletion script for {remote} verified message(s)."
            )
            self.confirm_button.configure(text="Copy Deletion Script", state="normal")
        else:
            self.delete_status_var.set("Deletion script is blocked by archive coverage checks.")
            self.confirm_button.configure(text="Copy Deletion Script", state="disabled")

    def _confirm(self) -> None:
        plan = self.plan
        if plan is None or not plan.safe_to_execute:
            return
        count = len(plan.remote_candidate_ids)
        if not self.deletion_confirmed:
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
            self.deletion_confirmed = True
        try:
            copied = bool(self.actions.copy_remote_delete_execute(plan))
        except Exception as error:
            messagebox.showerror("Remote Deletion", str(error), parent=self)
            return
        if not copied:
            return
        self.confirm_button.configure(text="Copy Deletion Script Again", state="normal")
        self.delete_status_var.set(
            "Deletion script copied. Paste and run it in the SAME conversation's DevTools console."
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
