"""Small first-stage GUI for the Discord provider."""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gpt_exporter.providers.discord import DiscordProvider


class DiscordProviderApp:
    """Inspect a native Discord data package through the provider adapter."""

    def __init__(self, root: tk.Tk, initial_source: Path | None = None) -> None:
        self.root = root
        self.root.title("Discord Provider")
        self.root.geometry("760x470")
        self.provider = DiscordProvider()
        self.source_var = tk.StringVar(value=str(initial_source or ""))
        self.status_var = tk.StringVar(
            value="Choose an extracted Discord data package, then click Analyze."
        )
        self._build()
        if initial_source:
            self.root.after_idle(self.analyze)

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Discord", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "Native Discord data package provider. This first implementation reads "
                "the Messages section and normalizes each channel into the shared canonical model."
            ),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))

        source_row = ttk.Frame(frame)
        source_row.pack(fill="x")
        ttk.Label(source_row, text="Data package:").pack(side="left")
        ttk.Entry(source_row, textvariable=self.source_var).pack(
            side="left", fill="x", expand=True, padx=(8, 8)
        )
        ttk.Button(source_row, text="Browse...", command=self.browse).pack(side="left")
        ttk.Button(source_row, text="Analyze", command=self.analyze).pack(side="left", padx=(8, 0))

        ttk.Label(frame, textvariable=self.status_var).pack(anchor="w", pady=(14, 8))

        columns = ("channel", "messages", "created", "updated")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.tree.heading("channel", text="Conversation")
        self.tree.heading("messages", text="Messages")
        self.tree.heading("created", text="First message")
        self.tree.heading("updated", text="Last message")
        self.tree.column("channel", width=320, anchor="w")
        self.tree.column("messages", width=80, anchor="e")
        self.tree.column("created", width=140, anchor="w")
        self.tree.column("updated", width=140, anchor="w")
        self.tree.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text=(
                "Note: Discord's native data package contains only messages sent by your account; "
                "the provider does not invent messages from other participants."
            ),
            wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

    def browse(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Choose extracted Discord data package",
        )
        if selected:
            self.source_var.set(selected)

    def analyze(self) -> None:
        source_text = self.source_var.get().strip()
        if not source_text:
            messagebox.showwarning("Discord Provider", "Choose a Discord data package first.", parent=self.root)
            return
        source = Path(source_text)
        if not source.exists():
            messagebox.showerror("Discord Provider", f"Path does not exist:\n{source}", parent=self.root)
            return

        self.status_var.set("Scanning Discord message transcripts...")
        self.root.update_idletasks()
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            sources = tuple(self.provider.discover(source))
            conversations = [self.provider.normalize(path) for path in sources]
        except Exception as error:  # surfaced in UI with the concrete provider context
            messagebox.showerror("Discord Provider", str(error), parent=self.root)
            self.status_var.set("Analysis failed.")
            return

        message_count = sum(len(conversation.messages) for conversation in conversations)
        for conversation in conversations:
            self.tree.insert(
                "",
                "end",
                values=(
                    conversation.title,
                    len(conversation.messages),
                    conversation.created_at or "",
                    conversation.updated_at or "",
                ),
            )
        self.status_var.set(
            f"Conversations: {len(conversations)}    Messages: {message_count}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect a Discord native data package")
    parser.add_argument("source", nargs="?", help="Optional extracted Discord data package path")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = tk.Tk()
    DiscordProviderApp(root, Path(arguments.source) if arguments.source else None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
