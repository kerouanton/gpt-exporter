"""Help and About dialogs for GPT Exporter."""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from ninec_app_toolkit import AppIdentity, show_about_dialog as show_shared_about_dialog

from gpt_exporter.version import APP_NAME, REPOSITORY_URL, display_version


APP_IDENTITY = AppIdentity(name=APP_NAME)


def show_about_dialog(
    parent: tk.Misc,
    *,
    on_user_guide: Callable[[], object] | None = None,
    on_history: Callable[[], object] | None = None,
) -> tk.Toplevel:
    """Open the shared 9c About dialog using GPT Exporter metadata.

    ``on_user_guide`` and ``on_history`` are retained for API compatibility.
    Those actions already remain available directly from the Help menu.
    """

    del on_user_guide, on_history
    return show_shared_about_dialog(
        parent,
        identity=APP_IDENTITY,
        app_version=display_version(),
        repository_url=REPOSITORY_URL,
    )


__all__ = ["show_about_dialog"]
