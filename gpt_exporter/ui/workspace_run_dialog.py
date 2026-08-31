"""Provider-neutral archive-run dialog for one selected workspace."""

from __future__ import annotations

import queue
import shutil
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from gpt_exporter.workflow import WorkspaceWorkflow


LATEST_ARCHIVE_LOG_NAME = "archive-workflow-latest.log"


def latest_archive_log_path(report_directory: Path) -> Path:
    return Path(report_directory) / LATEST_ARCHIVE_LOG_NAME


def create_archive_log_path(report_directory: Path, *, when: datetime | None = None) -> Path:
    report_directory = Path(report_directory)
    report_directory.mkdir(parents=True, exist_ok=True)
    timestamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    candidate = report_directory / f"archive-workflow-{timestamp}.log"
    suffix = 2
    while candidate.exists():
        candidate = report_directory / f"archive-workflow-{timestamp}-{suffix}.log"
        suffix += 1
    return candidate


def _queued_progress(events: queue.Queue[tuple[str, object]], message: str) -> None:
    text = str(message)
    if not text.endswith("\n"):
        text += "\n"
    events.put(("line", text))


def _run_worker(
    events: queue.Queue[tuple[str, object]],
    *,
    workspace_workflow: WorkspaceWorkflow,
    source_bundle: Path | None,
    legacy_root: Path,
) -> None:
    try:
        workspace_workflow.run_archive(
            source_bundle=source_bundle,
            legacy_root=legacy_root,
            progress=lambda message: _queued_progress(events, message),
        )
    except Exception as error:
        _queued_progress(events, f"\nERROR: {error}")
        events.put(("done", 1))
        return
    events.put(("done", 0))


class WorkspaceArchiveRunDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        *,
        workspace_workflow: WorkspaceWorkflow,
        source_bundle: Path | None = None,
        legacy_root: Path | str = Path.cwd(),
        on_success=None,
        auto_close_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.workspace_workflow = workspace_workflow
        self.workspace = workspace_workflow.workspace
        self.archive_root = workspace_workflow.archive_root
        self.source_bundle = Path(source_bundle) if source_bundle is not None else None
        self.legacy_root = Path(legacy_root)
        self.on_success = on_success
        self.auto_close_ms = auto_close_ms
        self.log_directory = workspace_workflow.paths.reports
        self.log_path: Path | None = None
        self._log_handle = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.finished = False

        self.title(f"Archive Workflow — {self.workspace.display_name}")
        self.geometry("900x620")
        self.minsize(700, 420)
        self.transient(parent)
        self.status_var = tk.StringVar(value="Starting archive workflow…")

        ttk.Label(self, textvariable=self.status_var, padding=(10, 10, 10, 6)).pack(fill="x")
        frame = ttk.Frame(self, padding=(10, 0, 10, 8))
        frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(frame, wrap="none", state="disabled")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        buttons = ttk.Frame(self, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")
        self.close_button = ttk.Button(buttons, text="Close", command=self.destroy, state="disabled")
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close_requested)
        self._open_log()
        self.after(50, self._start_worker)

    def _append_widget(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self._append_widget(text)
        if self._log_handle is not None:
            try:
                self._log_handle.write(text)
                self._log_handle.flush()
            except OSError:
                self._log_handle = None

    def _open_log(self) -> None:
        try:
            self.log_path = create_archive_log_path(self.log_directory)
            self._log_handle = self.log_path.open("w", encoding="utf-8", newline="")
        except OSError as error:
            self._append_widget(f"WARNING: Persistent workflow log unavailable: {error}\n\n")

    def _finalize_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.flush()
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        if self.log_path is not None:
            try:
                shutil.copyfile(self.log_path, latest_archive_log_path(self.log_directory))
            except OSError as error:
                self._append_widget(f"\nWARNING: Could not update latest workflow log: {error}\n")

    def _start_worker(self) -> None:
        self._append_log(f"> workspace: {self.workspace.display_name}\n")
        self._append_log(f"> provider: {self.workspace_workflow.provider.key}\n")
        self._append_log(f"> archive root: {self.archive_root}\n")
        if self.source_bundle is not None:
            self._append_log(f"> source bundle: {self.source_bundle}\n")
        self._append_log("\n")
        self.worker = threading.Thread(
            target=_run_worker,
            kwargs={
                "events": self.events,
                "workspace_workflow": self.workspace_workflow,
                "source_bundle": self.source_bundle,
                "legacy_root": self.legacy_root,
            },
            daemon=True,
            name=f"exporter-{self.workspace_workflow.provider.key}-archive-worker",
        )
        try:
            self.worker.start()
        except RuntimeError as error:
            self.events.put(("line", f"\nERROR: {error}\n"))
            self.events.put(("done", 1))
        self.after(50, self._drain_events)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self._append_log(str(payload))
                continue
            if kind != "done":
                continue
            self.finished = True
            return_code = int(payload)
            refresh_succeeded = False
            if return_code == 0:
                self.status_var.set("Archive completed; refreshing Browser…")
                try:
                    refresh_succeeded = True if self.on_success is None else bool(self.on_success())
                except Exception as error:
                    self._append_log(f"\nERROR: Browser refresh callback failed: {error}\n")
                if refresh_succeeded:
                    self.status_var.set("Archive workflow completed successfully. Closing…")
                    self._append_log("\nGUI: Browser refresh completed successfully.\n")
                else:
                    self.status_var.set("Archive completed, but Browser refresh failed.")
            else:
                self.status_var.set(f"Archive workflow failed (exit code {return_code}).")
            self._finalize_log()
            self.close_button.configure(state="normal")
            if return_code == 0 and refresh_succeeded:
                self.after(self.auto_close_ms, self.destroy)
        if not self.finished:
            self.after(100, self._drain_events)

    def _close_requested(self) -> None:
        if self.finished:
            self.destroy()
        else:
            self.bell()
            self.status_var.set("Archive workflow is still running; wait for it to finish.")


__all__ = [
    "WorkspaceArchiveRunDialog",
    "create_archive_log_path",
    "latest_archive_log_path",
]
