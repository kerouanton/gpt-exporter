import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Small GUI for validating and importing normalized legacy DOCX turns."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gpt_exporter.index._legacy_indexer import DEFAULT_DATABASE_PATH
from gpt_exporter.legacy.sqlite_import import (
    LEGACY_SQLITE_IMPORT_VERSION,
    import_legacy_collection,
    validate_legacy_collection,
)


def backup_database(database_path: Path) -> Path | None:
    """Create a consistent SQLite backup before a destructive import."""
    database_path = Path(database_path)
    if not database_path.is_file():
        return None
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database_path.with_name(
        f"{database_path.stem}-before-legacy-{timestamp}{database_path.suffix}"
    )
    source = sqlite3.connect(database_path)
    destination = sqlite3.connect(backup)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup


class LegacyImportWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Legacy DOCX Import")
        self.minsize(760, 420)

        self.turns_var = tk.StringVar(value=str(Path.cwd() / "legacy-docx-turns.json"))
        self.docx_root_var = tk.StringVar(value=r"F:\GPT")
        self.database_var = tk.StringVar(value=str(DEFAULT_DATABASE_PATH))
        self.status_var = tk.StringVar(value="Select the validated turns JSON and source DOCX directory.")
        self.validation: dict[str, int] | None = None
        self.payload: dict[str, object] | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self._path_row(frame, 0, "Turns JSON", self.turns_var, self._browse_turns)
        self._path_row(frame, 1, "DOCX root", self.docx_root_var, self._browse_docx_root)
        self._path_row(frame, 2, "SQLite database", self.database_var, self._browse_database)

        note = (
            "This GUI imports an already validated normalized legacy-turns file. "
            "It does not modify the original DOCX files and does not attempt to infer roles itself."
        )
        ttk.Label(frame, text=note, wraplength=700, justify="left").grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(12, 8)
        )

        actions = ttk.Frame(frame)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(4, 8))
        ttk.Button(actions, text="Validate", command=self.validate).pack(side="left")
        self.apply_button = ttk.Button(actions, text="Apply Import", command=self.apply, state="disabled")
        self.apply_button.pack(side="left", padx=8)

        ttk.Separator(frame).grid(row=5, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        ttk.Label(frame, textvariable=self.status_var, justify="left", wraplength=700).grid(
            row=6, column=0, columnspan=3, sticky="nw"
        )

        self.output = tk.Text(frame, height=12, wrap="word", state="disabled")
        self.output.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(7, weight=1)

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, padx=(8, 0), pady=4)

    def _browse_turns(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Select normalized legacy turns JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if chosen:
            self.turns_var.set(chosen)
            self._invalidate()

    def _browse_docx_root(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Select directory containing legacy DOCX files")
        if chosen:
            self.docx_root_var.set(chosen)
            self._invalidate()

    def _browse_database(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Select ChatGPT archive SQLite database",
            filetypes=[("SQLite databases", "*.sqlite"), ("All files", "*.*")],
        )
        if chosen:
            self.database_var.set(chosen)
            self._invalidate()

    def _invalidate(self) -> None:
        self.validation = None
        self.payload = None
        self.apply_button.configure(state="disabled")
        self.status_var.set("Paths changed. Validate again before importing.")

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def validate(self) -> None:
        try:
            turns_path = Path(self.turns_var.get()).expanduser().resolve()
            docx_root = Path(self.docx_root_var.get()).expanduser().resolve()
            if not turns_path.is_file():
                raise FileNotFoundError(f"Turns JSON not found: {turns_path}")
            if not docx_root.is_dir():
                raise FileNotFoundError(f"DOCX root not found: {docx_root}")
            payload = json.loads(turns_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Turns JSON root must be an object")
            validation = validate_legacy_collection(payload, docx_root=docx_root)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.validation = None
            self.payload = None
            self.apply_button.configure(state="disabled")
            self.status_var.set("Validation failed.")
            self._set_output(str(error))
            messagebox.showerror("Legacy DOCX Import", str(error), parent=self)
            return

        self.validation = validation
        self.payload = payload
        self.apply_button.configure(state="normal")
        summary = (
            f"Legacy SQLite importer: {LEGACY_SQLITE_IMPORT_VERSION}\n"
            f"Validated conversations: {validation['conversations']}\n"
            f"Validated turns: {validation['turns']}\n"
            f"Validation failures: {validation['failed']}\n"
            "SQLite was not modified."
        )
        self.status_var.set("Validation succeeded. Review the counts before applying.")
        self._set_output(summary)

    def apply(self) -> None:
        if self.validation is None or self.payload is None:
            messagebox.showinfo("Legacy DOCX Import", "Validate first.", parent=self)
            return

        database = Path(self.database_var.get()).expanduser().resolve()
        docx_root = Path(self.docx_root_var.get()).expanduser().resolve()
        confirmation = (
            f"Import {self.validation['conversations']} legacy conversations "
            f"({self.validation['turns']} turns) into:\n\n{database}\n\n"
            "A consistent SQLite backup will be created first. Continue?"
        )
        if not messagebox.askyesno("Apply Legacy Import", confirmation, parent=self):
            return

        try:
            backup = backup_database(database)
            counts = import_legacy_collection(
                self.payload,
                database_path=database,
                docx_root=docx_root,
                force=True,
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            self.status_var.set("Import failed.")
            self._set_output(str(error))
            messagebox.showerror("Legacy DOCX Import", str(error), parent=self)
            return

        result = (
            f"Updated conversations: {counts['updated']}\n"
            f"Unchanged conversations: {counts['unchanged']}\n"
            f"Indexed turns: {counts['turns']}\n"
            f"Failed conversations: {counts['failed']}\n"
            f"Database: {database}\n"
            f"Backup: {backup if backup else 'new database; no previous file'}"
        )
        self.status_var.set("Legacy import completed successfully.")
        self._set_output(result)
        messagebox.showinfo("Legacy DOCX Import", "Legacy import completed successfully.", parent=self)


def main() -> int:
    LegacyImportWindow().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
