"""Shared workspace shell extension for provider-specific remote cleanup actions."""

from __future__ import annotations

import tkinter as tk
from typing import Any

from gpt_exporter.ui.provider_manager_dialog import show_provider_manager
from gpt_exporter.ui.remote_delete import RemoteDeletionDialog
from gpt_exporter.ui.workspace_shell import ConversationWorkspaceApp


class RemoteDeletionWorkspaceApp(ConversationWorkspaceApp):
    """Conversation workspace with provider management and remote cleanup entry points."""

    REMOTE_DELETE_MENU_LABEL = "Delete / Clean Remote Conversation…"

    def _build_menu(self) -> None:
        super()._build_menu()
        menu_name = str(self.cget("menu"))
        menu_bar = self.nametowidget(menu_name)
        tools_menu = tk.Menu(menu_bar, tearoff=False)
        tools_menu.add_command(label="Providers…", command=self.show_providers)
        menu_bar.add_cascade(label="Tools", menu=tools_menu)

    def _build_ui(self) -> None:
        super()._build_ui()
        # Keep file actions first, destructive remote actions isolated, then projects.
        self.context_menu.insert_separator(2)
        self.context_menu.insert_command(
            3,
            label=self.REMOTE_DELETE_MENU_LABEL,
            command=self.remote_delete_selected,
            state="disabled",
        )

    def show_providers(self) -> None:
        show_provider_manager(self)

    def _remote_delete_supported(self, row: dict[str, Any]) -> bool:
        actions = self.provider_actions
        checker = getattr(actions, "remote_delete_supported", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(row))
        except Exception:
            return False

    def _configure_remote_delete_menu(self, row: dict[str, Any]) -> None:
        actions = self.provider_actions
        label = str(
            getattr(actions, "remote_delete_label", None)
            or self.REMOTE_DELETE_MENU_LABEL
        )
        self.context_menu.entryconfigure(
            3,
            label=label,
            state="normal" if self._remote_delete_supported(row) else "disabled",
        )

    def _show_context_menu(self, event: tk.Event) -> None:
        row_id = self.conversation_tree.identify_row(event.y)
        if not row_id:
            return
        self.conversation_tree.selection_set(row_id)
        self.conversation_tree.focus(row_id)
        self._conversation_selected()
        row = self.rows_by_iid.get(row_id)
        if row:
            self._configure_remote_delete_menu(row)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def remote_delete_selected(self) -> None:
        row = self._selected_row()
        if not row or not self._remote_delete_supported(row):
            return
        actions = self.provider_actions
        if actions is None:
            return
        RemoteDeletionDialog(self, row=row, actions=actions)


__all__ = ["RemoteDeletionWorkspaceApp"]
