import os
import queue
import shutil
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from gpt_exporter.pipeline import archive_bundle

ROOT = Path(__file__).resolve().parent
COLLECTOR_PATH = ROOT / "collect_chatgpt_archive.js"
SOURCE_BUNDLE_NAME = "chatgpt-archive-source.json"
CHATGPT_URL = "https://chatgpt.com/"
LATEST_ARCHIVE_LOG_NAME = "archive-workflow-latest.log"


def windows_download_directories() -> list[Path]:
    """Return likely Windows Downloads locations in deterministic order."""
    candidates: list[Path] = []

    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Downloads")

    home_drive = os.environ.get("HOMEDRIVE")
    home_path = os.environ.get("HOMEPATH")
    if home_drive and home_path:
        candidates.append(Path(f"{home_drive}{home_path}") / "Downloads")

    candidates.append(Path.home() / "Downloads")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(str(candidate)))
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def find_latest_source_bundle(
    directories: list[Path] | None = None,
    *,
    name: str = SOURCE_BUNDLE_NAME,
) -> Path | None:
    """Return the newest non-empty collector bundle in the supplied directories."""
    matches: list[Path] = []
    for directory in directories or windows_download_directories():
        candidate = Path(directory) / name
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                matches.append(candidate)
        except OSError:
            continue
    if not matches:
        return None
    return max(matches, key=lambda path: path.stat().st_mtime)


def source_bundle_signature(path: Path | None) -> tuple[str, int, int] | None:
    """Return a stable signature used to distinguish a newly downloaded bundle."""
    if path is None:
        return None
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    return (
        os.path.normcase(os.path.abspath(str(path))),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def read_collector_source(path: Path = COLLECTOR_PATH) -> str:
    """Read the browser collector exactly as stored in the application directory."""
    source = Path(path).read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"Collector JavaScript is empty: {path}")
    return source


def open_chatgpt() -> bool:
    """Open ChatGPT in the user's default browser."""
    return bool(webbrowser.open(CHATGPT_URL, new=2))


def latest_archive_log_path(report_directory: Path) -> Path:
    """Return the stable path used for the most recent archive-workflow log."""
    return Path(report_directory) / LATEST_ARCHIVE_LOG_NAME


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


def should_auto_close_archive(return_code: int, refresh_succeeded: bool) -> bool:
    """Only close automatically after both archive and Browser refresh succeeded."""
    return return_code == 0 and refresh_succeeded


def _queued_progress(
    events: queue.Queue[tuple[str, object]],
    message: str,
) -> None:
    """Translate one pipeline progress message into the GUI event stream."""
    text = str(message)
    if not text.endswith("\n"):
        text += "\n"
    events.put(("line", text))


def run_archive_pipeline_worker(
    events: queue.Queue[tuple[str, object]],
    *,
    archive_root: Path,
    source_bundle: Path | None,
    legacy_root: Path = ROOT,
) -> None:
    """Run the synchronous archive library on a worker thread.

    This function deliberately knows nothing about Tk widgets.  Progress and
    completion are transferred through ``events`` so the Tk thread remains the
    only thread that updates GUI state.
    """

    try:
        archive_bundle(
            archive_root=Path(archive_root),
            source_bundle=Path(source_bundle) if source_bundle is not None else None,
            legacy_root=Path(legacy_root),
            progress=lambda message: _queued_progress(events, message),
        )
    except Exception as error:  # Worker boundary: surface every failure to the GUI log.
        _queued_progress(events, f"\nERROR: {error}")
        events.put(("done", 1))
        return

    events.put(("done", 0))


class ArchiveRunDialog(tk.Toplevel):
    """Run the archive library on a worker thread without blocking Tk."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        archive_root: Path,
        source_bundle: Path | None = None,
        on_success=None,
        log_directory: Path | None = None,
        auto_close_ms: int = 1000,
    ) -> None:
        super().__init__(parent)
        self.title("Archive Workflow")
        self.geometry("900x620")
        self.minsize(700, 420)
        self.transient(parent)

        self.archive_root = Path(archive_root)
        self.source_bundle = Path(source_bundle) if source_bundle is not None else None
        self.on_success = on_success
        self.auto_close_ms = auto_close_ms
        self.log_directory = Path(log_directory) if log_directory is not None else None
        self.log_path: Path | None = None
        self._log_handle = None
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.finished = False
        self.status_var = tk.StringVar(value="Starting archive workflow…")

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
        self.close_button = ttk.Button(buttons, text="Close", command=self.destroy, state="disabled")
        self.close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._close_requested)
        self._open_persistent_log()
        self.after(50, self._start_worker)

    def _append_log_widget(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self._append_log_widget(text)
        if self._log_handle is None:
            return
        try:
            self._log_handle.write(text)
            self._log_handle.flush()
        except OSError as error:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None
            self._append_log_widget(f"\nWARNING: Persistent workflow log write failed: {error}\n")

    def _open_persistent_log(self) -> None:
        if self.log_directory is None:
            return
        try:
            self.log_path = create_archive_log_path(self.log_directory)
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

        if self.log_path is None or self.log_directory is None:
            return

        latest_path = latest_archive_log_path(self.log_directory)
        try:
            shutil.copyfile(self.log_path, latest_path)
        except OSError as error:
            self._append_log_widget(f"\nWARNING: Could not update latest workflow log: {error}\n")

    def _start_worker(self) -> None:
        self._append_log("> in-process: gpt_exporter.pipeline.archive_bundle()\n")
        self._append_log(f"> archive root: {self.archive_root}\n")
        if self.source_bundle is not None:
            self._append_log(f"> source bundle: {self.source_bundle}\n")
        self._append_log("\n")

        self.worker = threading.Thread(
            target=run_archive_pipeline_worker,
            kwargs={
                "events": self.events,
                "archive_root": self.archive_root,
                "source_bundle": self.source_bundle,
                "legacy_root": ROOT,
            },
            daemon=True,
            name="gpt-exporter-archive-worker",
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
            elif kind == "error":
                self.finished = True
                self.status_var.set("Archive workflow could not be started.")
                self._append_log(f"\nERROR: {payload}\n")
                self._finalize_persistent_log()
                self.close_button.configure(state="normal")
            elif kind == "done":
                self.finished = True
                return_code = int(payload)
                refresh_succeeded = False

                if return_code == 0:
                    self.status_var.set("Archive completed; refreshing Browser…")
                    if self.on_success is None:
                        refresh_succeeded = True
                    else:
                        try:
                            refresh_succeeded = bool(self.on_success())
                        except Exception as error:  # GUI callback boundary: keep diagnostics visible.
                            self._append_log(f"\nERROR: Browser refresh callback failed: {error}\n")
                            refresh_succeeded = False

                    if refresh_succeeded:
                        self.status_var.set("Archive workflow completed successfully. Closing…")
                        self._append_log("\nGUI: Browser refresh completed successfully.\n")
                    else:
                        self.status_var.set("Archive completed, but Browser refresh failed.")
                        self._append_log(
                            "\nGUI: Browser refresh failed; keeping this window open for diagnosis.\n"
                        )
                else:
                    self.status_var.set(f"Archive workflow failed (exit code {return_code}).")
                    self._append_log(f"\nGUI: Archive workflow failed with exit code {return_code}.\n")

                self._finalize_persistent_log()
                self.close_button.configure(state="normal")

                if should_auto_close_archive(return_code, refresh_succeeded):
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
    """Guide the user from browser collection to the local archive workflow."""

    POLL_MS = 1000

    def __init__(
        self,
        parent: tk.Misc,
        *,
        on_open_chatgpt,
        on_copy_collector,
        on_run_archive,
    ) -> None:
        super().__init__(parent)
        self.title("Archive New Conversations")
        self.geometry("760x360")
        self.minsize(640, 280)
        self.resizable(True, True)
        self.transient(parent)

        self.on_open_chatgpt = on_open_chatgpt
        self.on_copy_collector = on_copy_collector
        self.on_run_archive = on_run_archive
        self.collector_var = tk.StringVar(value="Preparing collector JavaScript…")
        self.bundle_var = tk.StringVar(value="Waiting for a new chatgpt-archive-source.json in Downloads…")
        self._poll_after_id: str | None = None
        self._archive_started = False
        self._initial_bundle_signature = source_bundle_signature(find_latest_source_bundle())

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Archive New Conversations",
            font=("TkDefaultFont", 12, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        self._step(
            body,
            "1. Open ChatGPT",
            "Open ChatGPT in your normal browser and make sure you are signed in.",
        )
        ttk.Button(body, text="Open ChatGPT", command=self.on_open_chatgpt).pack(
            anchor="w", pady=(0, 10)
        )

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
            "When the collector finishes, the browser downloads chatgpt-archive-source.json. "
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

        bundle = find_latest_source_bundle()
        signature = source_bundle_signature(bundle)
        if bundle is None:
            self.bundle_var.set("Waiting for a new chatgpt-archive-source.json in Downloads…")
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
        bundle = find_latest_source_bundle()
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
        self._initial_bundle_signature = source_bundle_signature(bundle)
        self.bundle_var.set("Archive workflow did not start; waiting for another new bundle…")
        self._poll_after_id = self.after(self.POLL_MS, self._check_bundle)
