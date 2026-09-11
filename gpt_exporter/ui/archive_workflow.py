"""Provider-neutral UI for browser-collector archive workflows."""

from __future__ import annotations

import queue
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Protocol


_AUTO_CLOSE_SUCCESSFUL_PROCESSING_WINDOWS = True


def processing_windows_auto_close_enabled() -> bool:
    """Return the session-wide auto-close preference for successful backlogs."""
    return _AUTO_CLOSE_SUCCESSFUL_PROCESSING_WINDOWS


def set_processing_windows_auto_close(enabled: bool) -> None:
    """Set the session-wide auto-close preference for successful backlogs."""
    global _AUTO_CLOSE_SUCCESSFUL_PROCESSING_WINDOWS
    _AUTO_CLOSE_SUCCESSFUL_PROCESSING_WINDOWS = bool(enabled)


@dataclass(frozen=True, slots=True)
class ArchiveWorkflowSpec:
    """Provider-supplied copy for the shared archive workflow dialog."""

    service_label: str
    open_instructions: str
    collector_instructions: str
    download_instructions: str
    waiting_text: str


class ArchiveWorkflowActions(Protocol):
    """Provider capabilities consumed by the shared archive workflow UI."""

    archive_workflow_spec: ArchiveWorkflowSpec

    def open_service(self) -> None: ...
    def copy_collector(self) -> bool: ...
    def snapshot_exports(self) -> Any: ...
    def find_new_export(self, snapshot: Any) -> Path | None: ...
    def process_export(self, path: Path) -> bool: ...
    def run_export(self, path: Path, progress: Callable[[str], None]) -> Any: ...
    def finish_export(self, result: Any) -> bool: ...


def latest_archive_log_path(report_directory: Path) -> Path:
    """Return the stable path used for the most recent shared archive-workflow log."""
    return Path(report_directory) / "archive-workflow-latest.log"


def create_archive_log_path(
    report_directory: Path,
    *,
    when: datetime | None = None,
) -> Path:
    """Create a unique timestamped path for one archive-workflow run."""
    report_directory = Path(report_directory)
    report_directory.mkdir(parents=True, exist_ok=True)
    timestamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    candidate = report_directory / f"archive-workflow-{timestamp}.log"
    suffix = 2
    while candidate.exists():
        candidate = report_directory / f"archive-workflow-{timestamp}-{suffix}.log"
        suffix += 1
    return candidate


class ArchiveProcessingDialog(tk.Toplevel):
    """Run provider archive processing on a worker and show one shared backlog."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        actions: ArchiveWorkflowActions,
        export_path: Path,
        auto_close_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.title("Archive Workflow")
        self.geometry("900x620")
        self.minsize(700, 420)
        self.transient(parent)

        self.actions = actions
        self.export_path = Path(export_path)
        self.auto_close_ms = auto_close_ms
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.finished = False
        self.status_var = tk.StringVar(value="Starting archive workflow…")
        self.auto_close_var = tk.BooleanVar(value=processing_windows_auto_close_enabled())
        self.log_path: Path | None = None
        self._log_handle = None

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
        ttk.Checkbutton(
            buttons,
            text="Automatically close successful processing windows",
            variable=self.auto_close_var,
            command=self._auto_close_preference_changed,
        ).pack(side="left")
        self.close_button = ttk.Button(buttons, text="Close", command=self.destroy, state="disabled")
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close_requested)
        self._open_persistent_log()
        self.after(50, self._start_worker)

    def _auto_close_preference_changed(self) -> None:
        set_processing_windows_auto_close(self.auto_close_var.get())

    def _report_directory(self) -> Path | None:
        value = getattr(self.actions, "workflow_log_directory", None)
        return Path(value) if value is not None else None

    def _open_persistent_log(self) -> None:
        directory = self._report_directory()
        if directory is None:
            return
        try:
            self.log_path = create_archive_log_path(directory)
            self._log_handle = self.log_path.open("w", encoding="utf-8", newline="")
        except OSError as error:
            self.log_path = None
            self._log_handle = None
            self._append_log_widget(f"WARNING: Persistent workflow log unavailable: {error}\n\n")

    def _finalize_persistent_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.flush()
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
        directory = self._report_directory()
        if self.log_path is None or directory is None:
            return
        try:
            shutil.copyfile(self.log_path, latest_archive_log_path(directory))
        except OSError as error:
            self._append_log_widget(f"\nWARNING: Could not update latest workflow log: {error}\n")

    def _append_log_widget(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        if not text.endswith("\n"):
            text += "\n"
        self._append_log_widget(text)
        if self._log_handle is not None:
            try:
                self._log_handle.write(text)
                self._log_handle.flush()
            except OSError:
                self._log_handle = None

    def _start_worker(self) -> None:
        self.status_var.set(f"Processing {self.actions.archive_workflow_spec.service_label} export…")
        self._append_log(f"> provider: {self.actions.archive_workflow_spec.service_label}")
        self._append_log(f"> source export: {self.export_path}")
        self._append_log("")

        def worker() -> None:
            try:
                result = self.actions.run_export(
                    self.export_path,
                    lambda message: self.events.put(("line", str(message))),
                )
            except Exception as error:
                self.events.put(("error", error))
                return
            self.events.put(("done", result))

        self.worker = threading.Thread(
            target=worker,
            daemon=True,
            name="gpt-exporter-shared-archive-worker",
        )
        try:
            self.worker.start()
        except RuntimeError as error:
            self.events.put(("error", error))
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

            if kind == "error":
                self.finished = True
                self.status_var.set("Archive workflow failed.")
                self._append_log(f"\nERROR: {payload}")
                self._finalize_persistent_log()
                self.close_button.configure(state="normal")
                continue

            if kind == "done":
                self.finished = True
                self.status_var.set("Archive completed; refreshing Browser…")
                refresh_succeeded = False
                try:
                    refresh_succeeded = bool(self.actions.finish_export(payload))
                except Exception as error:
                    self._append_log(f"\nERROR: Browser refresh callback failed: {error}")

                if refresh_succeeded:
                    if self.auto_close_var.get():
                        self.status_var.set("Archive workflow completed successfully. Closing…")
                    else:
                        self.status_var.set("Archive workflow completed successfully.")
                    self._append_log("\nGUI: Browser refresh completed successfully.")
                else:
                    self.status_var.set("Archive completed, but Browser refresh failed.")
                    self._append_log("\nGUI: Browser refresh failed; keeping this window open for diagnosis.")
                self._finalize_persistent_log()
                self.close_button.configure(state="normal")
                if refresh_succeeded and self.auto_close_var.get():
                    self.after(self.auto_close_ms, self._auto_close_after_success)

        if not self.finished:
            self.after(100, self._drain_events)

    def _auto_close_after_success(self) -> None:
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass

    def _close_requested(self) -> None:
        if self.finished:
            self.destroy()
            return
        self.bell()
        self.status_var.set("Archive workflow is still running; wait for it to finish.")


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

        ttk.Label(body, text="Archive New Conversations", font=("TkDefaultFont", 12, "bold")).pack(
            anchor="w", pady=(0, 10)
        )

        self._step(body, f"1. Open {self.spec.service_label}", self.spec.open_instructions)
        ttk.Button(body, text=f"Open {self.spec.service_label}", command=self.actions.open_service).pack(
            anchor="w", pady=(0, 10)
        )

        self._step(body, "2. Run the collector", self.spec.collector_instructions)
        collector_row = ttk.Frame(body)
        collector_row.pack(fill="x", pady=(0, 10))
        ttk.Label(collector_row, textvariable=self.collector_var).pack(side="left")
        ttk.Button(collector_row, text="Copy Again", command=self._copy_collector).pack(side="right")

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


__all__ = [
    "ArchiveProcessingDialog",
    "ArchiveWorkflowActions",
    "ArchiveWorkflowDialog",
    "ArchiveWorkflowSpec",
    "create_archive_log_path",
    "latest_archive_log_path",
    "processing_windows_auto_close_enabled",
    "set_processing_windows_auto_close",
]
