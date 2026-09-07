import os
import queue
import shutil
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from gpt_exporter.providers.gpt.pipeline import archive_bundle
from gpt_exporter.providers.gpt.resources import collector_path


def _application_root() -> Path:
    """Return the historical application/repository root after provider relocation."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[4]


ROOT = _application_root()
COLLECTOR_PATH = collector_path()
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
    """Read the packaged collector script and reject missing/empty resources."""
    source = Path(path).read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"Collector resource is empty: {path}")
    return source


def open_chatgpt() -> None:
    """Open ChatGPT in the user's default browser."""
    webbrowser.open(CHATGPT_URL)


def create_archive_log_path(reports_dir: Path, *, when: datetime | None = None) -> Path:
    """Return a unique timestamped archive log path."""
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (when or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
    candidate = reports_dir / f"archive-workflow-{timestamp}.log"
    counter = 2
    while candidate.exists():
        candidate = reports_dir / f"archive-workflow-{timestamp}-{counter}.log"
        counter += 1
    return candidate


def latest_archive_log_path(reports_dir: Path) -> Path:
    """Return the stable path for the most recent archive workflow log."""
    return Path(reports_dir) / LATEST_ARCHIVE_LOG_NAME


def _queue_progress(events: queue.Queue[tuple[str, object]], line: str) -> None:
    events.put(("line", line + ("" if line.endswith("\n") else "\n")))


def run_archive_pipeline_worker(
    events: queue.Queue[tuple[str, object]],
    *,
    archive_root: Path,
    source_bundle: Path | None,
    convert_only: bool = False,
    fresh: bool = False,
    skip_assets: bool = False,
    delete_source: bool = True,
) -> None:
    """Run the provider archive pipeline in a worker thread and queue UI events."""
    try:
        archive_bundle(
            archive_root=archive_root,
            source_bundle=source_bundle,
            convert_only=convert_only,
            fresh=fresh,
            skip_assets=skip_assets,
            delete_source=delete_source,
            legacy_root=ROOT,
            progress=lambda line: _queue_progress(events, line),
        )
    except Exception as exc:  # UI worker must report failures instead of dying silently.
        _queue_progress(events, f"ERROR: {exc}")
        events.put(("done", 1))
        return
    events.put(("done", 0))


def should_auto_close_archive(exit_code: int, refresh_succeeded: bool) -> bool:
    return exit_code == 0 and refresh_succeeded


class ArchiveRunDialog(tk.Toplevel):
    """Minimal modal progress dialog for the ChatGPT archive workflow."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        archive_root: Path,
        source_bundle: Path | None,
        on_complete=None,
    ) -> None:
        super().__init__(master)
        self.title("Archive ChatGPT")
        self.geometry("800x500")
        self.archive_root = Path(archive_root)
        self.source_bundle = Path(source_bundle) if source_bundle else None
        self.on_complete = on_complete
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        self.output = tk.Text(frame, wrap="word")
        self.output.pack(fill="both", expand=True)
        self.close_button = ttk.Button(frame, text="Close", command=self.destroy, state="disabled")
        self.close_button.pack(anchor="e", pady=(8, 0))

        self.after(50, self._drain_events)
        threading.Thread(target=self._start_worker, daemon=True).start()

    def _start_worker(self) -> None:
        run_archive_pipeline_worker(
            self.events,
            archive_root=self.archive_root,
            source_bundle=self.source_bundle,
        )

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "line":
                    self.output.insert("end", str(payload))
                    self.output.see("end")
                elif kind == "done":
                    self.close_button.configure(state="normal")
                    succeeded = int(payload) == 0
                    refreshed = True
                    if self.on_complete is not None:
                        try:
                            refresh_result = self.on_complete(succeeded)
                            if refresh_result is False:
                                refreshed = False
                        except Exception:
                            refreshed = False
                    if should_auto_close_archive(int(payload), refreshed):
                        self.destroy()
                        return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(50, self._drain_events)
