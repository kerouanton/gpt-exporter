"""Provider-neutral Tk selector for conversation applications."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections.abc import Iterable

from gpt_exporter.core import ProviderDescriptor


def provider_choices(descriptors: Iterable[ProviderDescriptor]) -> tuple[ProviderDescriptor, ...]:
    """Return descriptors in stable display order."""
    return tuple(
        sorted(
            descriptors,
            key=lambda item: (item.display_name.casefold(), item.provider_id),
        )
    )


class ProviderSelectorDialog(tk.Toplevel):
    """Modal provider chooser with no dependency on concrete providers."""

    def __init__(
        self,
        parent: tk.Misc,
        descriptors: Iterable[ProviderDescriptor],
        *,
        default_provider_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Choose Provider")
        self.resizable(False, False)
        self.result: str | None = None
        self._descriptors = provider_choices(descriptors)
        self._by_label = {
            f"{descriptor.display_name} ({descriptor.provider_id})": descriptor.provider_id
            for descriptor in self._descriptors
        }

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Choose a conversation provider",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(body, text="Provider:").pack(anchor="w")
        self.provider_var = tk.StringVar()
        self.combo = ttk.Combobox(
            body,
            textvariable=self.provider_var,
            state="readonly",
            width=38,
            values=tuple(self._by_label),
        )
        self.combo.pack(fill="x", pady=(4, 14))

        selected_label = next(
            (
                label
                for label, provider_id in self._by_label.items()
                if provider_id == default_provider_id
            ),
            next(iter(self._by_label), ""),
        )
        if selected_label:
            self.provider_var.set(selected_label)

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
        """Map the dialog first, then make it modal.

        On Windows, making a toplevel transient to a withdrawn root can leave the
        modal window unmapped while ``wait_window`` keeps the process alive.  The
        selector deliberately uses a hidden short-lived root, so this dialog must
        be an independent top-level window and only acquire its grab after it is
        viewable.
        """
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.wait_visibility()
        self.grab_set()
        self.combo.focus_force()

    def _accept(self) -> None:
        provider_id = self._by_label.get(self.provider_var.get())
        if provider_id is None:
            return
        self.result = provider_id
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def choose_provider(
    descriptors: Iterable[ProviderDescriptor],
    *,
    default_provider_id: str | None = None,
) -> str | None:
    """Show a short-lived Tk root and return the selected provider id."""
    root = tk.Tk()
    root.withdraw()
    try:
        dialog = ProviderSelectorDialog(
            root,
            descriptors,
            default_provider_id=default_provider_id,
        )
        dialog.show_modal()
        root.wait_window(dialog)
        return dialog.result
    finally:
        root.destroy()
