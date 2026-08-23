"""Help and About dialogs for GPT Exporter."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable
import webbrowser

from gpt_exporter.version import APP_NAME, LICENSE_ID, REPOSITORY_URL, display_version


def show_about_dialog(
    parent: tk.Misc,
    *,
    on_user_guide: Callable[[], object] | None = None,
    on_history: Callable[[], object] | None = None,
) -> tk.Toplevel:
    """Open a compact About window using central application metadata."""

    window = tk.Toplevel(parent)
    window.title(f"About {APP_NAME}")
    window.resizable(False, False)
    window.transient(parent)

    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=APP_NAME, font="TkHeadingFont").pack(anchor="w")
    ttk.Label(frame, text=f"Version {display_version()}").pack(anchor="w", pady=(4, 12))
    ttk.Label(
        frame,
        text="Local ChatGPT archive, export, index and browser.",
        justify="left",
    ).pack(anchor="w")
    ttk.Label(frame, text=f"License: {LICENSE_ID}").pack(anchor="w", pady=(8, 14))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")
    if on_user_guide is not None:
        ttk.Button(buttons, text="User Guide", command=on_user_guide).pack(side="left")
    if on_history is not None:
        ttk.Button(buttons, text="Release History", command=on_history).pack(side="left", padx=(6, 0))
    ttk.Button(
        buttons,
        text="GitHub",
        command=lambda: webbrowser.open(REPOSITORY_URL),
    ).pack(side="left", padx=(6, 0))
    ttk.Button(buttons, text="Close", command=window.destroy).pack(side="right")

    window.bind("<Escape>", lambda _event: window.destroy())
    window.update_idletasks()
    try:
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - window.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - window.winfo_reqheight()) // 2)
        window.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    return window


__all__ = ["show_about_dialog"]
