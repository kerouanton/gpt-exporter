"""Tk selector for named conversation workspaces."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from tkinter import ttk

from gpt_exporter.workspaces import ConversationWorkspace


def workspace_choices(workspaces: Iterable[ConversationWorkspace]) -> tuple[ConversationWorkspace, ...]:
    """Return enabled workspaces in stable display order."""
    return tuple(
        sorted(
            (workspace for workspace in workspaces if workspace.enabled),
            key=lambda item: (item.name.casefold(), item.provider_id, str(item.root_path).casefold()),
        )
    )


class WorkspaceSelectorDialog(tk.Toplevel):
    """Modal named-workspace chooser with no concrete provider imports."""

    def __init__(
        self,
        parent: tk.Misc,
        workspaces: Iterable[ConversationWorkspace],
        *,
        default_workspace_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Choose Workspace")
        self.resizable(False, False)
        self.result: str | None = None
        self._workspaces = workspace_choices(workspaces)
        self._by_label = {
            f"{workspace.name} — {workspace.provider_id} — {workspace.root_path}": workspace.name
            for workspace in self._workspaces
        }

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Choose a conversation workspace",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(body, text="Workspace:").pack(anchor="w")
        self.workspace_var = tk.StringVar()
        self.combo = ttk.Combobox(
            body,
            textvariable=self.workspace_var,
            state="readonly",
            width=68,
            values=tuple(self._by_label),
        )
        self.combo.pack(fill="x", pady=(4, 14))

        selected_label = next(
            (
                label
                for label, workspace_name in self._by_label.items()
                if workspace_name.casefold() == (default_workspace_name or "").casefold()
            ),
            next(iter(self._by_label), ""),
        )
        if selected_label:
            self.workspace_var.set(selected_label)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right")
        self.open_button = ttk.Button(buttons, text="Open", command=self._accept)
        self.open_button.pack(side="right", padx=(0, 8))
        if not self._by_label:
            self.open_button.configure(state="disabled")

        self.bind("<Return>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def show_modal(self) -> None:
        """Map before grabbing so the hidden-root Windows case remains safe."""
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.wait_visibility()
        self.grab_set()
        self.combo.focus_force()

    def _accept(self) -> None:
        workspace_name = self._by_label.get(self.workspace_var.get())
        if workspace_name is None:
            return
        self.result = workspace_name
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def choose_workspace(
    workspaces: Iterable[ConversationWorkspace],
    *,
    default_workspace_name: str | None = None,
    parent: tk.Misc | None = None,
) -> str | None:
    """Show a workspace chooser and return the selected workspace name.

    Startup can still use the historical short-lived hidden root. When an
    application window already exists, pass it as ``parent`` so Tk does not
    create a second root/main window while the first one is active.
    """
    owns_root = parent is None
    root: tk.Misc
    if owns_root:
        hidden_root = tk.Tk()
        hidden_root.withdraw()
        root = hidden_root
    else:
        root = parent

    try:
        dialog = WorkspaceSelectorDialog(
            root,
            workspaces,
            default_workspace_name=default_workspace_name,
        )
        dialog.show_modal()
        root.wait_window(dialog)
        return dialog.result
    finally:
        if owns_root:
            hidden_root.destroy()


__all__ = ["WorkspaceSelectorDialog", "choose_workspace", "workspace_choices"]
