"""Guided Discord provider GUI using an authenticated browser session."""

from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from gpt_exporter.providers.discord.archive import archive_collector_export, default_archive_root
from gpt_exporter.providers.discord.collector import (
    CollectorExport,
    collector_javascript,
    open_discord,
    snapshot_exports,
    wait_for_new_export,
)
from gpt_exporter.providers.discord.provider import DiscordProvider


class DiscordProviderApp:
    """Collect and archive the currently displayed Discord DM."""

    def __init__(self, root: tk.Tk, *, archive_root: Path | None = None) -> None:
        self.root = root
        self.root.title("Discord Provider")
        self.root.geometry("780x520")
        self.root.minsize(700, 440)
        self.provider = DiscordProvider()
        self.download_directory = Path.home() / "Downloads"
        self.archive_root = Path(archive_root or default_archive_root()).expanduser()
        self.status_var = tk.StringVar(value="Ready.")
        self.collector_var = tk.StringVar(value="Collector not armed.")
        self.archive_var = tk.StringVar(value=f"Archive: {self.archive_root}")
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._watch_thread: threading.Thread | None = None
        self._build()
        self.root.after(150, self._poll_events)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Discord", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Archive the currently displayed Discord DM through your existing browser session. "
                "No Discord token, password or cookie is read by the application."
            ),
            wraplength=730,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        steps = ttk.LabelFrame(frame, text="Archive Current DM", padding=12)
        steps.pack(fill="x")

        ttk.Label(
            steps,
            text="1. Open Discord and select the DM you want to archive.",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(steps, text="Open Discord", command=self._open_discord).grid(
            row=0, column=1, sticky="e", padx=(12, 0)
        )

        ttk.Label(
            steps,
            text=(
                "2. Click Start Archive. The collector JavaScript is copied to the clipboard and "
                "the application starts watching Downloads."
            ),
            wraplength=590,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Button(steps, text="Start Archive…", command=self.start_archive).grid(
            row=1, column=1, sticky="e", padx=(12, 0), pady=(10, 0)
        )

        ttk.Label(
            steps,
            text=(
                "3. In Discord press F12, open Console, paste with Ctrl+V and run. "
                "The resulting JSON is detected, normalized and archived automatically."
            ),
            wraplength=590,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Button(steps, text="Copy Collector Again", command=self.copy_collector).grid(
            row=2, column=1, sticky="e", padx=(12, 0), pady=(10, 0)
        )
        steps.columnconfigure(0, weight=1)

        ttk.Label(frame, textvariable=self.collector_var).pack(anchor="w", pady=(12, 2))
        ttk.Label(frame, textvariable=self.archive_var).pack(anchor="w", pady=(0, 8))

        columns = ("conversation", "messages", "first", "last", "status")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=8)
        self.tree.heading("conversation", text="Conversation")
        self.tree.heading("messages", text="Messages")
        self.tree.heading("first", text="First message")
        self.tree.heading("last", text="Last message")
        self.tree.heading("status", text="Archive status")
        self.tree.column("conversation", width=260, anchor="w")
        self.tree.column("messages", width=75, anchor="e")
        self.tree.column("first", width=145, anchor="w")
        self.tree.column("last", width=145, anchor="w")
        self.tree.column("status", width=110, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=(4, 8))

        ttk.Separator(frame).pack(fill="x", pady=(2, 8))
        ttk.Label(frame, textvariable=self.status_var, wraplength=730, justify="left").pack(anchor="w")

    def _open_discord(self) -> None:
        try:
            if open_discord():
                self.status_var.set("Discord opened in your browser.")
            else:
                self.status_var.set("Browser launch was not confirmed; open Discord manually if necessary.")
        except Exception as error:
            messagebox.showerror("Discord Provider", str(error), parent=self.root)

    def copy_collector(self) -> None:
        try:
            script = collector_javascript()
            self.root.clipboard_clear()
            self.root.clipboard_append(script)
            self.root.update()
            self.collector_var.set("Collector JavaScript copied to clipboard.")
        except Exception as error:
            messagebox.showerror("Discord Provider", str(error), parent=self.root)

    def start_archive(self) -> None:
        if self._watch_thread is not None and self._watch_thread.is_alive():
            self.copy_collector()
            self.status_var.set("Archive watcher is already running; collector copied again.")
            return
        try:
            known = snapshot_exports(self.download_directory)
            self.copy_collector()
        except Exception as error:
            messagebox.showerror("Discord Provider", str(error), parent=self.root)
            return

        self.status_var.set(
            f"Waiting for a new Discord DM export in {self.download_directory}…"
        )
        self.collector_var.set(
            "Collector armed. Select the DM in Discord, then run the copied JavaScript in DevTools Console."
        )
        self._watch_thread = threading.Thread(
            target=self._watch_export,
            args=(known,),
            name="discord-provider-export-watch",
            daemon=True,
        )
        self._watch_thread.start()

    def _watch_export(self, known: set[Path]) -> None:
        try:
            summary = wait_for_new_export(
                self.download_directory,
                known_files=known,
            )
            self._events.put(("export", summary))
        except Exception as error:
            self._events.put(("error", error))

    def _poll_events(self) -> None:
        try:
            while True:
                event, value = self._events.get_nowait()
                if event == "export":
                    assert isinstance(value, CollectorExport)
                    self._process_export(value)
                elif event == "error":
                    assert isinstance(value, Exception)
                    self.status_var.set(f"Discord export failed: {value}")
                    messagebox.showerror("Discord Provider", str(value), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _process_export(self, summary: CollectorExport) -> None:
        self.status_var.set(
            f"Export detected: {summary.message_count} messages. Normalizing and archiving…"
        )
        self.root.update_idletasks()
        try:
            conversation = self.provider.normalize(summary.path)
            result = archive_collector_export(summary.path, archive_root=self.archive_root)
        except Exception as error:
            self.status_var.set(f"Archive failed: {error}")
            messagebox.showerror("Discord Provider", str(error), parent=self.root)
            return

        self.tree.insert(
            "",
            "end",
            values=(
                conversation.title,
                len(conversation.messages),
                conversation.created_at or "",
                conversation.updated_at or "",
                "Updated" if result.updated else "Preserved",
            ),
        )
        self.status_var.set(
            f"Discord DM archived successfully. DOCX: {result.docx_path}"
            if result.updated
            else "Incoming export was incomplete compared with the existing archive; existing conversation preserved."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive the currently displayed Discord DM through a browser collector"
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=default_archive_root(),
        help=f"Discord archive root (default: {default_archive_root()})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = tk.Tk()
    DiscordProviderApp(root, archive_root=arguments.archive_root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
