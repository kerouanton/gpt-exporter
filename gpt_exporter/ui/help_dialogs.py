"""Help and About dialogs for GPT Exporter."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable
import webbrowser

from gpt_exporter.version import APP_NAME, REPOSITORY_URL, display_version


def _show_fallback_about(parent: tk.Misc) -> tk.Toplevel:
    """Keep standalone/public builds usable when 9c_app_toolkit is unavailable."""

    window = tk.Toplevel(parent)
    window.title(f"About {APP_NAME}")
    window.resizable(False, False)
    window.transient(parent)

    frame = ttk.Frame(window, padding=18)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text=APP_NAME, font="TkHeadingFont").pack(anchor="w")
    version_label = ttk.Label(frame, text=f"Version {display_version()}", cursor="hand2")
    version_label.pack(anchor="w", pady=(4, 14))
    version_label.bind("<Button-1>", lambda _event: webbrowser.open(REPOSITORY_URL))
    ttk.Button(frame, text="Close", command=window.destroy).pack()

    window.bind("<Escape>", lambda _event: window.destroy())
    return window


def show_about_dialog(
    parent: tk.Misc,
    *,
    on_user_guide: Callable[[], object] | None = None,
    on_history: Callable[[], object] | None = None,
) -> tk.Toplevel:
    """Open the shared 9c About dialog using GPT Exporter metadata.

    ``on_user_guide`` and ``on_history`` are retained for API compatibility.
    Those actions already remain available directly from the Help menu.

    GPT Exporter is public while 9c_app_toolkit is currently private, so the
    toolkit import intentionally happens only when About is opened. Standalone
    environments without the private toolkit retain a small functional fallback.
    """

    del on_user_guide, on_history

    try:
        from ninec_app_toolkit import AppIdentity, show_about_dialog as show_shared_about_dialog
    except ModuleNotFoundError:
        return _show_fallback_about(parent)

    return show_shared_about_dialog(
        parent,
        identity=AppIdentity(name=APP_NAME),
        app_version=display_version(),
        repository_url=REPOSITORY_URL,
    )


__all__ = ["show_about_dialog"]
