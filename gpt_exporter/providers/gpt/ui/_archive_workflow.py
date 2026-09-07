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
from gpt_exporter.providers.gpt.resources import collector_path

ROOT = Path(__file__).resolve().parent
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


def read_collector_source() -> str:
    """Read the collector JavaScript from its packaged provider resource."""
    source = COLLECTOR_PATH.read_text(encoding="utf-8")
    if not source.strip():
        raise ValueError(f"Collector resource is empty: {COLLECTOR_PATH}")
    return source


def source_bundle_signature(path: Path) -> tuple[int, int] | None:
    """Return a cheap file signature for change detection."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_size, stat.st_mtime_ns


def find_latest_source_bundle() -> Path | None:
    """Find the newest non-empty ChatGPT collector bundle in Downloads."""
    candidates: list[Path] = []
    for directory in windows_download_directories():
        try:
            for candidate in directory.glob(SOURCE_BUNDLE_NAME):
                if candidate.is_file() and candidate.stat().st_size > 0:
                    candidates.append(candidate)
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def create_archive_log_path(log_directory: Path) -> Path:
    """Create one unique timestamped archive log path."""
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return log_directory / f"archive-workflow-{timestamp}.log"


def latest_archive_log_path(log_directory: Path) -> Path:
    """Return the stable path of the latest archive workflow log."""
    return log_directory / LATEST_ARCHIVE_LOG_NAME


def _write_log_line(handle, message: str) -> None:
    handle.write(message)
    if not message.endswith("\n"):
        handle.write("\n")
    handle.flush()


def _copy_latest_log(log_path: Path, stable_path: Path) -> None:
    stable_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(log_path, stable_path)


def _run_archive_worker(
    source_bundle: Path,
    archive_root: Path,
    events: queue.Queue,
    *,
    fresh: bool = False,
    convert_only: bool = False,
    skip_assets: bool = False,
    auto_close: bool = False,
) -> None:
    """Run the provider archive pipeline without touching Tk from the worker."""
    logs_dir = archive_root / "logs"
    log_path = create_archive_log_path(logs_dir)
    latest_log = latest_archive_log_path(logs_dir)

    def progress(message: str = "") -> None:
        events.put(("progress", message))
        _write_log_line(log_handle, message)

    success = False
    with log_path.open("w", encoding="utf-8", newline="\n") as log_handle:
        try:
            result = archive_bundle(
                source_bundle=source_bundle,
                archive_root=archive_root,
                fresh=fresh,
                convert_only=convert_only,
                skip_assets=skip_assets,
                progress=progress,
            )
            success = bool(result.index_result)
            events.put(("complete", result, auto_close))
        except Exception as exc:
            progress(f"ERROR: {exc}")
            events.put(("error", exc))
        finally:
            try:
                _copy_latest_log(log_path, latest_log)
            except OSError:
                pass

    if auto_close and success:
        events.put(("close", None))


def open_archive_dialog(parent, *, archive_root: Path, source_bundle: Path | None = None):
    """Open the ChatGPT archive workflow dialog."""
    dialog = tk.Toplevel(parent)
    dialog.title("Archive ChatGPT conversations")
    dialog.transient(parent)
    dialog.geometry("820x620")

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)

    instructions = ttk.Label(
        frame,
        text=(
            "Open ChatGPT in your browser, paste the collector into DevTools, "
            "save the downloaded bundle, then run the archive workflow."
        ),
        wraplength=760,
        justify="left",
    )
    instructions.pack(fill="x", pady=(0, 8))

    button_row = ttk.Frame(frame)
    button_row.pack(fill="x", pady=(0, 8))

    ttk.Button(button_row, text="Open ChatGPT", command=lambda: webbrowser.open(CHATGPT_URL)).pack(
        side="left", padx=(0, 6)
    )

    def copy_collector() -> None:
        source = read_collector_source()
        dialog.clipboard_clear()
        dialog.clipboard_append(source)
        dialog.update()

    ttk.Button(button_row, text="Copy collector", command=copy_collector).pack(side="left")

    log = tk.Text(frame, wrap="word", height=24)
    log.pack(fill="both", expand=True)

    events: queue.Queue = queue.Queue()
    selected_bundle = source_bundle or find_latest_source_bundle()

    def append(message: str) -> None:
        log.insert("end", message + ("\n" if not message.endswith("\n") else ""))
        log.see("end")

    def poll_events() -> None:
        try:
            while True:
                kind, payload, *rest = events.get_nowait()
                if kind == "progress":
                    append(str(payload))
                elif kind == "error":
                    append(f"Archive failed: {payload}")
                elif kind == "complete":
                    append("Archive completed successfully.")
                elif kind == "close":
                    dialog.destroy()
                    return
        except queue.Empty:
            pass
        if dialog.winfo_exists():
            dialog.after(100, poll_events)

    def start() -> None:
        nonlocal selected_bundle
        if selected_bundle is None or not selected_bundle.is_file():
            selected_bundle = find_latest_source_bundle()
        if selected_bundle is None:
            append(f"No {SOURCE_BUNDLE_NAME} bundle found in Downloads.")
            return
        append(f"Using source bundle: {selected_bundle}")
        worker = threading.Thread(
            target=_run_archive_worker,
            args=(selected_bundle, archive_root, events),
            daemon=True,
        )
        worker.start()

    ttk.Button(frame, text="Run archive", command=start).pack(anchor="e", pady=(8, 0))
    dialog.after(100, poll_events)
    return dialog
