"""Public ChatGPT archive-workflow API after provider relocation.

The historical GUI implementation is retained byte-for-byte in
``_archive_workflow``. This adapter fixes path semantics that depended on the
old repository-root location and binds provider-local pipeline/resources.
"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import gpt_exporter.resources as _generic_resources
from export_provider_chatgpt.export.repair import (
    find_missing_docx_sources,
    regenerate_missing_docx as _provider_regenerate_missing_docx,
)
from export_provider_chatgpt.pipeline import archive_bundle as _provider_archive_bundle
from export_provider_chatgpt.resources import collector_path as _provider_collector_path

# The historical implementation still imports ``collector_path`` from the old
# generic resources namespace. Bind that name from inside the provider before
# importing the retained implementation; the generic resources module itself
# remains provider-neutral and contains no ChatGPT resource or dependency.
_generic_resources.collector_path = _provider_collector_path

from . import _archive_workflow as _implementation


def _application_root() -> Path:
    """Return the same application/repository root used before relocation."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[5]


ROOT = _application_root()
COLLECTOR_PATH = _provider_collector_path()

# Rebind globals used dynamically by methods in the historical implementation.
_implementation.ROOT = ROOT
_implementation.COLLECTOR_PATH = COLLECTOR_PATH
_implementation.archive_bundle = _provider_archive_bundle

_original_worker = _implementation.run_archive_pipeline_worker
_original_read_collector_source = _implementation.read_collector_source


def run_archive_pipeline_worker(
    events,
    *,
    archive_root: Path,
    source_bundle: Path | None,
    legacy_root: Path = ROOT,
) -> None:
    """Run the worker with the pre-relocation application root by default."""
    # Preserve the historical patch/test surface: callers may replace the
    # public ``archive_bundle`` attribute on this module before invoking the
    # worker. The retained implementation resolves its own module global.
    _implementation.archive_bundle = archive_bundle
    return _original_worker(
        events,
        archive_root=archive_root,
        source_bundle=source_bundle,
        legacy_root=legacy_root,
    )


def read_collector_source(path: Path = COLLECTOR_PATH) -> str:
    """Read the collector from the ChatGPT provider resource directory."""
    return _original_read_collector_source(path)


# Methods on the historical Tk classes resolve these names from their defining
# module, so update that module as well as this public facade.
_implementation.run_archive_pipeline_worker = run_archive_pipeline_worker
_implementation.read_collector_source = read_collector_source

for _name in dir(_implementation):
    if not _name.startswith("_") and _name not in {
        "ROOT",
        "COLLECTOR_PATH",
        "run_archive_pipeline_worker",
        "read_collector_source",
    }:
        globals()[_name] = getattr(_implementation, _name)


def regenerate_missing_docx(
    archive_root: Path | str,
    *,
    progress=None,
):
    """Public GUI-facing binding for local missing-DOCX repair."""

    return _provider_regenerate_missing_docx(archive_root, progress=progress)


def run_missing_docx_repair_worker(
    events: queue.Queue[tuple[str, object]],
    *,
    archive_root: Path,
) -> None:
    """Run local DOCX repair on a worker thread and report through a queue."""

    def progress(message: str) -> None:
        text = str(message)
        if not text.endswith("\n"):
            text += "\n"
        events.put(("line", text))

    try:
        result = regenerate_missing_docx(
            Path(archive_root),
            progress=progress,
        )
    except Exception as error:  # Worker boundary: surface every failure to Tk.
        progress(f"\nERROR: {error}")
        events.put(("error", error))
        return

    events.put(("done", result))


class MissingDocxRepairDialog(tk.Toplevel):
    """Regenerate missing DOCX outputs from existing archived JSON/XZ files."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        archive_root: Path,
        on_success=None,
    ) -> None:
        super().__init__(parent)
        self.title("Regenerate Missing DOCX")
        self.geometry("850x520")
        self.minsize(650, 380)
        self.transient(parent)

        self.archive_root = Path(archive_root)
        self.on_success = on_success
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.finished = False
        self.status_var = tk.StringVar(value="Preparing DOCX repair…")

        ttk.Label(self, textvariable=self.status_var, padding=(10, 10, 10, 6)).pack(
            fill="x"
        )

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
        self.close_button = ttk.Button(
            buttons,
            text="Close",
            command=self.destroy,
            state="disabled",
        )
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close_requested)
        self.after(50, self._start_worker)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_worker(self) -> None:
        self.status_var.set("Scanning archive and regenerating missing DOCX files…")
        self._append_log(f"> archive root: {self.archive_root}\n\n")
        self.worker = threading.Thread(
            target=run_missing_docx_repair_worker,
            kwargs={
                "events": self.events,
                "archive_root": self.archive_root,
            },
            daemon=True,
            name="gpt-exporter-missing-docx-repair",
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
                self.status_var.set("DOCX repair failed.")
                self.close_button.configure(state="normal")
                continue

            if kind == "done":
                self.finished = True
                result = payload
                refresh_succeeded = True
                if not result.success:
                    self.status_var.set("DOCX repair completed with export failures.")
                    self._append_log("\nDOCX repair reported export failures.\n")
                else:
                    if self.on_success is not None:
                        try:
                            refresh_succeeded = bool(self.on_success())
                        except Exception as error:
                            refresh_succeeded = False
                            self._append_log(f"\nERROR: Browser refresh failed: {error}\n")
                    if not result.missing_sources:
                        self.status_var.set("No missing DOCX files were found.")
                    elif refresh_succeeded:
                        self.status_var.set(
                            f"DOCX repair completed: {result.repaired_count} file(s) regenerated."
                        )
                    else:
                        self.status_var.set("DOCX files regenerated, but Browser refresh failed.")
                self.close_button.configure(state="normal")

        if not self.finished:
            self.after(100, self._drain_events)

    def _close_requested(self) -> None:
        if self.finished:
            self.destroy()
            return
        self.bell()
        self.status_var.set("DOCX repair is still running; wait for it to finish.")


__all__ = [
    name
    for name in globals()
    if not name.startswith("_")
    and name not in {"queue", "sys", "threading", "Path", "tk", "ttk"}
]
