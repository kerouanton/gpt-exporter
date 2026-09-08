import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

"""Graphical browser for the ChatGPT archive SQLite index.

MVP goals:
- browse and sort conversations,
- full-text search with a lightweight Everything-like syntax and combined filters,
- project tree built from slash-separated work-project names,
- virtual Unprojected / Multiple projects audit views,
- direct or recursive project-branch filtering,
- visible internal drag-and-drop from a conversation to any project branch,
- refreshes preserve active filters, selection and scroll position,
- double-click to open the DOCX,
- reveal and select the DOCX directly in the system file manager,
- details + matching-message preview,
- clickable lightweight keyword/tag cloud,
- project-tree context menu with sub-project / rename / delete operations.

The application uses only Python's standard library and the schema created by
index_chatgpt_archive.py.  It does not modify JSON or DOCX archive files.
"""

import argparse
import json
import logging
import math
import subprocess
import sys
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

import archive_core as core


DEBUG = True
LOGGER = logging.getLogger("chatgpt_archive_browser")

DEFAULT_DATABASE_PATH = (
    Path(os.environ.get("USERPROFILE") or Path.home())
    / "Documents"
    / "ChatGPT Archive"
    / "conversations-index.sqlite"
)
STATE_PATH = Path.home() / ".chatgpt_archive_browser.json"
ALL_VALUE = "All"
PROJECT_VIEW_ALL = "__ALL__"
PROJECT_VIEW_UNPROJECTED = "__UNPROJECTED__"
PROJECT_VIEW_MULTIPLE = "__MULTIPLE__"
PROJECT_VIEW_PROJECT = "__PROJECT__"


def configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    LOGGER.debug("Debug logging enabled: %s", debug)


def open_with_default_application(path_value: str | None) -> None:
    if not path_value:
        raise FileNotFoundError("No file path is recorded for this conversation.")
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    LOGGER.debug("Opening file: %s", path)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def reveal_in_file_manager(path_value: str | None) -> None:
    """Reveal a file in the platform file manager, selecting it when possible."""
    if not path_value:
        raise FileNotFoundError("No file path is recorded for this conversation.")
    path = Path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    LOGGER.debug("Revealing file in file manager: %s", path)
    if os.name == "nt":
        # Explorer's legacy /select parser is picky about quoting.  Passing the
        # whole /select,<path> token through subprocess' argv quoting can make
        # Explorer ignore the target and fall back to Documents.  Use the exact
        # command-line form documented by Explorer instead.  Windows filenames
        # cannot contain a double quote, so this quoting is safe.
        normalized = os.path.normpath(str(path))
        command_line = f'explorer.exe /select,"{normalized}"'
        LOGGER.debug("Explorer command: %s", command_line)
        subprocess.Popen(command_line)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        # Linux file managers do not share one portable "select file" API.
        subprocess.Popen(["xdg-open", str(path.parent)])


def build_index_command(database_path: Path) -> list[str]:
    """Build the incremental indexer command for the browser's open database."""
    database_path = Path(database_path)
    archive_root = database_path.parent
    return [
        sys.executable,
        str(Path(__file__).resolve().parent / "index_chatgpt_archive.py"),
        "--archive-root",
        str(archive_root),
        "--downloads-dir",
        str(archive_root / "downloads"),
        "--database",
        str(database_path),
        "index",
    ]


class ArchiveBrowser(tk.Tk):
    def __init__(self, database_path: Path, *, debug: bool = False) -> None:
        super().__init__()
        self.database_path = Path(database_path)
        self.debug = debug
        self.title("ChatGPT Archive Browser")
        self.minsize(1180, 700)

        self.state_data = self._load_state()
        geometry = self.state_data.get("geometry", "1540x900")
        self.geometry(geometry)

        self.search_after_id: str | None = None
        self.current_rows: list[dict[str, Any]] = []
        self.rows_by_iid: dict[str, dict[str, Any]] = {}
        self.project_iid_to_name: dict[str, str | None] = {}
        # Every visual branch gets a semantic path, including synthetic branches
        # that are not themselves rows in work_projects.
        self.project_iid_to_path: dict[str, str | None] = {}
        self.drag_conversation_iid: str | None = None
        self.drag_target_iid: str | None = None
        self.drag_popup: tk.Toplevel | None = None
        self.drag_popup_label: ttk.Label | None = None
        self.project_drag_source_iid: str | None = None
        self.project_drag_source_path: str | None = None
        self.project_drag_press_root: tuple[int, int] | None = None
        self.project_drag_active = False
        self._suppress_project_selection_event = False
        self.sort_column = "date"
        self.sort_reverse = True

        self.search_var = tk.StringVar()
        self.origin_var = tk.StringVar(value=ALL_VALUE)
        self.project_var = tk.StringVar(value=ALL_VALUE)
        self.project_view = PROJECT_VIEW_ALL
        self.tag_var = tk.StringVar(value=ALL_VALUE)
        self.category_var = tk.StringVar(value=ALL_VALUE)
        self.recursive_var = tk.BooleanVar(value=bool(self.state_data.get("recursive", True)))
        self.status_var = tk.StringVar(value="Ready")

        self._validate_database()
        self._build_ui()
        self._refresh_filter_values()
        self._refresh_project_tree()
        self.refresh_conversations()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # State and startup
    # ------------------------------------------------------------------

    def _load_state(self) -> dict[str, Any]:
        try:
            if STATE_PATH.is_file():
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.warning("Could not read GUI state: %s", error)
        return {}

    def _save_state(self) -> None:
        data = {
            "geometry": self.geometry(),
            "database_path": str(self.database_path),
            "recursive": bool(self.recursive_var.get()),
        }
        try:
            STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as error:
            LOGGER.warning("Could not save GUI state: %s", error)

    def _validate_database(self) -> None:
        LOGGER.debug("Validating database: %s", self.database_path)
        with core.connect_database(self.database_path, readonly=True) as connection:
            count = connection.execute("SELECT COUNT(*) AS n FROM conversations").fetchone()["n"]
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        LOGGER.info("Database opened: schema v%d, %d conversations", version, count)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_menu()

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Search:").pack(side="left")
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=42)
        search_entry.pack(side="left", padx=(6, 12))
        search_entry.bind("<KeyRelease>", self._schedule_search_refresh)
        search_entry.bind("<Return>", lambda _event: self.refresh_conversations())

        ttk.Button(toolbar, text="Clear", command=self._clear_filters).pack(side="left", padx=(0, 14))

        ttk.Label(toolbar, text="Origin:").pack(side="left")
        self.origin_combo = ttk.Combobox(
            toolbar, textvariable=self.origin_var, state="readonly", width=23
        )
        self.origin_combo.pack(side="left", padx=(5, 10))
        self.origin_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_conversations())

        ttk.Label(toolbar, text="Tag:").pack(side="left")
        self.tag_combo = ttk.Combobox(
            toolbar, textvariable=self.tag_var, state="readonly", width=18
        )
        self.tag_combo.pack(side="left", padx=(5, 10))
        self.tag_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_conversations())

        ttk.Label(toolbar, text="Category:").pack(side="left")
        self.category_combo = ttk.Combobox(
            toolbar, textvariable=self.category_var, state="readonly", width=18
        )
        self.category_combo.pack(side="left", padx=(5, 10))
        self.category_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_conversations())

        ttk.Checkbutton(
            toolbar,
            text="Recursive",
            variable=self.recursive_var,
            command=self.refresh_conversations,
        ).pack(side="left", padx=(6, 0))

        main_pane = ttk.Panedwindow(self, orient="horizontal")
        main_pane.pack(fill="both", expand=True, padx=8, pady=(4, 6))

        self.left_frame = ttk.Frame(main_pane)
        self.center_frame = ttk.Frame(main_pane)
        self.right_frame = ttk.Frame(main_pane)
        main_pane.add(self.left_frame, weight=1)
        main_pane.add(self.center_frame, weight=4)
        main_pane.add(self.right_frame, weight=2)

        self._build_left_panel()
        self._build_conversation_table()
        self._build_details_panel()

        status = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken")
        status.pack(fill="x", side="bottom")

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Open DOCX", command=self.open_selected_docx)
        file_menu.add_command(label="Open in Explorer", command=self.open_selected_in_explorer)
        file_menu.add_separator()
        file_menu.add_command(label="Update Search Index", command=self.update_index)
        file_menu.add_separator()
        file_menu.add_command(label="Refresh", command=self._refresh_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menu_bar.add_cascade(label="File", menu=file_menu)

        project_menu = tk.Menu(menu_bar, tearoff=False)
        project_menu.add_command(label="New Project…", command=self.new_project)
        project_menu.add_command(label="Add Sub-project…", command=self.add_subproject)
        project_menu.add_command(label="Rename Selected Branch…", command=self.rename_selected_project)
        project_menu.add_command(label="Delete Selected Branch…", command=self.delete_selected_project)
        project_menu.add_separator()
        project_menu.add_command(label="Assign Selected Conversation…", command=self.assign_selected_conversation)
        project_menu.add_command(label="Remove Selected Project Assignment", command=self.remove_selected_project_assignment)
        menu_bar.add_cascade(label="Project", menu=project_menu)

        view_menu = tk.Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Clear Filters", command=self._clear_filters)
        view_menu.add_command(label="Refresh All", command=self._refresh_all)
        menu_bar.add_cascade(label="View", menu=view_menu)

        help_menu = tk.Menu(menu_bar, tearoff=False)
        help_menu.add_command(label="Search Syntax…", command=self.show_search_syntax)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menu_bar)

    def _build_left_panel(self) -> None:
        notebook = ttk.Notebook(self.left_frame)
        notebook.pack(fill="both", expand=True)

        project_tab = ttk.Frame(notebook, padding=4)
        cloud_tab = ttk.Frame(notebook, padding=4)
        notebook.add(project_tab, text="Projects")
        notebook.add(cloud_tab, text="Keywords")

        self.project_tree = ttk.Treeview(project_tab, show="tree", selectmode="browse")
        project_scroll = ttk.Scrollbar(project_tab, orient="vertical", command=self.project_tree.yview)
        self.project_tree.configure(yscrollcommand=project_scroll.set)
        self.project_tree.tag_configure("drop_target", background="#d9edf7")
        self.project_tree.pack(side="left", fill="both", expand=True)
        project_scroll.pack(side="right", fill="y")
        self.project_tree.bind("<<TreeviewSelect>>", self._project_tree_selected)
        self.project_tree.bind("<ButtonPress-1>", self._project_drag_start, add="+")
        self.project_tree.bind("<B1-Motion>", self._project_drag_motion, add="+")
        self.project_tree.bind("<ButtonRelease-1>", self._project_drag_end, add="+")
        self.project_tree.bind("<Button-3>", self._show_project_context_menu)

        self.project_context_menu = tk.Menu(self, tearoff=False)
        self.project_context_menu.add_command(label="Add Sub-project…", command=self.add_subproject)
        self.project_context_menu.add_command(label="Rename…", command=self.rename_selected_project)
        self.project_context_menu.add_command(label="Delete…", command=self.delete_selected_project)

        project_buttons = ttk.Frame(self.left_frame, padding=(4, 5, 4, 0))
        project_buttons.pack(fill="x")
        ttk.Button(project_buttons, text="New…", command=self.new_project).pack(side="left")
        ttk.Button(project_buttons, text="Rename…", command=self.rename_selected_project).pack(
            side="left", padx=4
        )

        self.keyword_canvas = tk.Canvas(cloud_tab, highlightthickness=0, background="white")
        cloud_scroll = ttk.Scrollbar(cloud_tab, orient="vertical", command=self.keyword_canvas.yview)
        self.keyword_canvas.configure(yscrollcommand=cloud_scroll.set)
        self.keyword_canvas.pack(side="left", fill="both", expand=True)
        cloud_scroll.pack(side="right", fill="y")
        self.keyword_canvas.bind("<Configure>", lambda _event: self._draw_keyword_cloud())

    def _build_conversation_table(self) -> None:
        columns = ("date", "title", "origin", "projects", "tags", "messages")
        self.conversation_tree = ttk.Treeview(
            self.center_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        headings = {
            "date": "Date",
            "title": "Title",
            "origin": "Origin",
            "projects": "Project(s)",
            "tags": "Tags",
            "messages": "Messages",
        }
        widths = {
            "date": 92,
            "title": 300,
            "origin": 170,
            "projects": 220,
            "tags": 180,
            "messages": 72,
        }
        anchors = {"messages": "e"}

        for column in columns:
            self.conversation_tree.heading(
                column,
                text=headings[column],
                command=lambda c=column: self.sort_by_column(c),
            )
            self.conversation_tree.column(
                column,
                width=widths[column],
                minwidth=60,
                anchor=anchors.get(column, "w"),
            )

        vertical = ttk.Scrollbar(
            self.center_frame, orient="vertical", command=self.conversation_tree.yview
        )
        horizontal = ttk.Scrollbar(
            self.center_frame, orient="horizontal", command=self.conversation_tree.xview
        )
        self.conversation_tree.configure(
            yscrollcommand=vertical.set,
            xscrollcommand=horizontal.set,
        )

        self.conversation_tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.center_frame.rowconfigure(0, weight=1)
        self.center_frame.columnconfigure(0, weight=1)

        self.conversation_tree.bind("<<TreeviewSelect>>", self._conversation_selected)
        self.conversation_tree.bind("<Double-1>", lambda _event: self.open_selected_docx())
        self.conversation_tree.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.conversation_tree.bind("<B1-Motion>", self._drag_motion, add="+")
        self.conversation_tree.bind("<ButtonRelease-1>", self._drag_end, add="+")

        self.context_menu = tk.Menu(self, tearoff=False)
        self.context_menu.add_command(label="Open DOCX", command=self.open_selected_docx)
        self.context_menu.add_command(label="Open in Explorer", command=self.open_selected_in_explorer)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Assign to Project…", command=self.assign_selected_conversation)
        self.context_menu.add_command(
            label="Remove Project Assignment…", command=self.remove_selected_project_assignment
        )
        self.conversation_tree.bind("<Button-3>", self._show_context_menu)

    def _build_details_panel(self) -> None:
        details = ttk.LabelFrame(self.right_frame, text="Conversation", padding=8)
        details.pack(fill="x")

        self.detail_title_var = tk.StringVar(value="—")
        self.detail_date_var = tk.StringVar(value="—")
        self.detail_origin_var = tk.StringVar(value="—")
        self.detail_count_var = tk.StringVar(value="—")

        ttk.Label(details, textvariable=self.detail_title_var, font=("TkDefaultFont", 10, "bold"), wraplength=340).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )
        self._detail_row(details, 1, "Date", self.detail_date_var)
        self._detail_row(details, 2, "Origin", self.detail_origin_var)
        self._detail_row(details, 3, "Messages", self.detail_count_var)

        action_frame = ttk.Frame(details)
        action_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        ttk.Button(action_frame, text="Open DOCX", command=self.open_selected_docx).pack(side="left")
        ttk.Button(
            action_frame,
            text="Open in Explorer",
            command=self.open_selected_in_explorer,
        ).pack(side="left", padx=5)

        project_box = ttk.LabelFrame(self.right_frame, text="Project assignments", padding=6)
        project_box.pack(fill="x", pady=(8, 0))
        self.detail_project_list = tk.Listbox(project_box, height=5, exportselection=False)
        self.detail_project_list.pack(fill="x")
        project_actions = ttk.Frame(project_box)
        project_actions.pack(fill="x", pady=(5, 0))
        ttk.Button(project_actions, text="Add…", command=self.assign_selected_conversation).pack(side="left")
        ttk.Button(
            project_actions,
            text="Remove",
            command=self.remove_selected_project_assignment,
        ).pack(side="left", padx=5)

        meta_box = ttk.LabelFrame(self.right_frame, text="Categories / tags", padding=6)
        meta_box.pack(fill="x", pady=(8, 0))
        self.detail_meta_var = tk.StringVar(value="—")
        ttk.Label(meta_box, textvariable=self.detail_meta_var, justify="left", wraplength=340).pack(
            fill="x"
        )

        preview_box = ttk.LabelFrame(self.right_frame, text="Message preview", padding=4)
        preview_box.pack(fill="both", expand=True, pady=(8, 0))
        self.preview_text = tk.Text(
            preview_box,
            wrap="word",
            height=18,
            state="disabled",
            padx=6,
            pady=6,
        )
        preview_scroll = ttk.Scrollbar(preview_box, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_scroll.set)
        self.preview_text.pack(side="left", fill="both", expand=True)
        preview_scroll.pack(side="right", fill="y")

    @staticmethod
    def _detail_row(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="nw", padx=(0, 8))
        ttk.Label(parent, textvariable=variable, wraplength=270).grid(row=row, column=1, sticky="nw")

    # ------------------------------------------------------------------
    # Refresh and filtering
    # ------------------------------------------------------------------

    def _refresh_filter_values(self) -> None:
        LOGGER.debug("Refreshing filter values")
        origins = [ALL_VALUE] + core.list_origins(self.database_path)
        tags = [ALL_VALUE] + core.list_tags(self.database_path)
        categories = [ALL_VALUE] + core.list_categories(self.database_path)
        project_rows = core.list_projects(self.database_path)

        self.origin_combo["values"] = origins
        self.tag_combo["values"] = tags
        self.category_combo["values"] = categories

        if self.origin_var.get() not in origins:
            self.origin_var.set(ALL_VALUE)
        if self.tag_var.get() not in tags:
            self.tag_var.set(ALL_VALUE)
        if self.category_var.get() not in categories:
            self.category_var.set(ALL_VALUE)

        # A selected branch may be purely visual (only descendants are concrete
        # work_projects rows), so validate against every semantic partial path.
        if self.project_view == PROJECT_VIEW_PROJECT:
            available_paths: set[str] = set()
            for row in project_rows:
                parts = core.project_path_parts(row["name"])
                for depth in range(1, len(parts) + 1):
                    available_paths.add(" / ".join(parts[:depth]).casefold())
            current = core.normalize_project_path(self.project_var.get()).casefold()
            if not current or current not in available_paths:
                self.project_var.set(ALL_VALUE)
                self.project_view = PROJECT_VIEW_ALL

    def _refresh_project_tree(self) -> None:
        """Rebuild the project tree without changing the active GUI filters."""
        LOGGER.debug("Refreshing project tree")
        selected_view = self.project_view
        selected_project = self.project_var.get()
        previous_yview = self.project_tree.yview()

        # Treeview emits <<TreeviewSelect>> even for programmatic selections.
        # Suppress that event while rebuilding so refreshes never change the
        # active view behind the user's back.
        self._suppress_project_selection_event = True
        self.project_tree.delete(*self.project_tree.get_children())
        self.project_iid_to_name.clear()
        self.project_iid_to_path.clear()

        all_iid = self.project_tree.insert("", "end", text="All conversations", open=True)
        unprojected_iid = self.project_tree.insert("", "end", text="Unprojected")
        multiple_iid = self.project_tree.insert("", "end", text="Multiple projects")
        root_iid = self.project_tree.insert("", "end", text="Projects", open=True)
        self.project_iid_to_name[all_iid] = PROJECT_VIEW_ALL
        self.project_iid_to_name[unprojected_iid] = PROJECT_VIEW_UNPROJECTED
        self.project_iid_to_name[multiple_iid] = PROJECT_VIEW_MULTIPLE
        self.project_iid_to_name[root_iid] = None
        self.project_iid_to_path[all_iid] = None
        self.project_iid_to_path[unprojected_iid] = None
        self.project_iid_to_path[multiple_iid] = None
        self.project_iid_to_path[root_iid] = ""

        path_to_iid: dict[tuple[str, ...], str] = {}
        exact_project_names = {row["name"] for row in core.list_projects(self.database_path)}

        for project_name in sorted(exact_project_names, key=str.casefold):
            parts = tuple(part.strip() for part in project_name.split("/") if part.strip())
            parent = root_iid
            for depth in range(1, len(parts) + 1):
                partial = parts[:depth]
                if partial not in path_to_iid:
                    iid = self.project_tree.insert(parent, "end", text=parts[depth - 1], open=True)
                    path_to_iid[partial] = iid
                    self.project_iid_to_name[iid] = None
                    self.project_iid_to_path[iid] = " / ".join(partial)
                parent = path_to_iid[partial]
            self.project_iid_to_name[parent] = project_name

        target_iid = all_iid
        if selected_view == PROJECT_VIEW_UNPROJECTED:
            target_iid = unprojected_iid
        elif selected_view == PROJECT_VIEW_MULTIPLE:
            target_iid = multiple_iid
        elif selected_view == PROJECT_VIEW_PROJECT and selected_project != ALL_VALUE:
            wanted = core.normalize_project_path(selected_project).casefold()
            for iid, candidate_path in self.project_iid_to_path.items():
                if candidate_path is None:
                    continue
                if core.normalize_project_path(candidate_path).casefold() == wanted:
                    target_iid = iid
                    break
            else:
                self.project_view = PROJECT_VIEW_ALL
                self.project_var.set(ALL_VALUE)

        self.project_tree.selection_set(target_iid)
        self.project_tree.focus(target_iid)
        self.project_tree.see(target_iid)
        if previous_yview:
            try:
                self.project_tree.yview_moveto(previous_yview[0])
            except tk.TclError:
                pass

        # Keep suppression active until queued virtual selection events have
        # been delivered by Tk.
        self.after_idle(self._release_project_selection_suppression)

    def _release_project_selection_suppression(self) -> None:
        self._suppress_project_selection_event = False

    def refresh_conversations(self) -> None:
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
            self.search_after_id = None

        project_filter = (
            self.project_var.get() if self.project_view == PROJECT_VIEW_PROJECT else ""
        )
        origin_filter = "" if self.origin_var.get() == ALL_VALUE else self.origin_var.get()
        tag_filter = "" if self.tag_var.get() == ALL_VALUE else self.tag_var.get()
        category_filter = "" if self.category_var.get() == ALL_VALUE else self.category_var.get()
        unprojected = self.project_view == PROJECT_VIEW_UNPROJECTED
        multiple_projects = self.project_view == PROJECT_VIEW_MULTIPLE
        recursive = bool(self.recursive_var.get())

        LOGGER.debug(
            "Refresh: search=%r origin=%r project=%r tag=%r category=%r "
            "view=%s recursive=%s",
            self.search_var.get(),
            origin_filter,
            project_filter,
            tag_filter,
            category_filter,
            self.project_view,
            recursive,
        )

        try:
            self.current_rows = core.query_conversations(
                self.database_path,
                search=self.search_var.get(),
                origin=origin_filter,
                project=project_filter,
                tag=tag_filter,
                category=category_filter,
                unprojected=unprojected,
                multiple_projects=multiple_projects,
                recursive_project=recursive,
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Search error", str(error), parent=self)
            return

        self._populate_conversation_tree()
        self._draw_keyword_cloud()

        count = len(self.current_rows)
        if self.project_view == PROJECT_VIEW_UNPROJECTED:
            label = "Unprojected"
        elif self.project_view == PROJECT_VIEW_MULTIPLE:
            label = "Multiple projects"
        elif self.project_view == PROJECT_VIEW_PROJECT:
            mode = "recursive" if recursive else "direct"
            label = f"{project_filter} — {mode}"
        else:
            label = "All conversations"
        self.status_var.set(f"{label} — {count} conversation(s)")

    def _populate_conversation_tree(self) -> None:
        """Populate rows while preserving selection and scroll position."""
        selected = self._selected_row()
        selected_conversation_id = selected.get("conversation_id") if selected else None
        previous_yview = self.conversation_tree.yview()
        previous_xview = self.conversation_tree.xview()

        self.conversation_tree.delete(*self.conversation_tree.get_children())
        self.rows_by_iid.clear()

        rows = list(self.current_rows)
        rows = self._sorted_rows(rows)

        selected_iid: str | None = None
        for row in rows:
            iid = self.conversation_tree.insert(
                "",
                "end",
                values=(
                    row["date_display"],
                    row["title"],
                    row["origin_display"],
                    row["projects_display"],
                    row["tags_display"],
                    row["message_count"],
                ),
            )
            self.rows_by_iid[iid] = row
            if row.get("conversation_id") == selected_conversation_id:
                selected_iid = iid

        if rows:
            target_iid = selected_iid or self.conversation_tree.get_children()[0]
            self.conversation_tree.selection_set(target_iid)
            self.conversation_tree.focus(target_iid)
            if selected_iid:
                self.conversation_tree.see(target_iid)
            else:
                if previous_yview:
                    self.conversation_tree.yview_moveto(previous_yview[0])
                if previous_xview:
                    self.conversation_tree.xview_moveto(previous_xview[0])
            self._conversation_selected()
        else:
            self._clear_details()

    def _schedule_search_refresh(self, _event: tk.Event) -> None:
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
        self.search_after_id = self.after(300, self.refresh_conversations)

    def _clear_filters(self) -> None:
        self.search_var.set("")
        self.origin_var.set(ALL_VALUE)
        self.project_var.set(ALL_VALUE)
        self.project_view = PROJECT_VIEW_ALL
        self.tag_var.set(ALL_VALUE)
        self.category_var.set(ALL_VALUE)
        # Recursive is a navigation preference, not a content filter.
        self._refresh_project_tree()
        self.refresh_conversations()

    def show_search_syntax(self) -> None:
        messagebox.showinfo(
            "Search Syntax",
            "Search syntax (Everything-inspired):\n\n"
            "word word    AND\n"
            "!word        NOT\n"
            "word | word  OR\n"
            "< ... >      grouping\n"
            '"words here" exact phrase\n\n'
            "Plain words are prefix searches.\n\n"
            "Example:\n"
            "<kenton | haken> firmware !ghidra",
            parent=self,
        )

    def _refresh_all(self) -> None:
        self._refresh_filter_values()
        self._refresh_project_tree()
        self.refresh_conversations()

    def update_index(self) -> None:
        """Run the incremental indexer and reload Browser views on success."""
        command = build_index_command(self.database_path)
        LOGGER.info("Updating archive search index")
        LOGGER.debug("Indexer command: %r", command)
        self.status_var.set("Updating search index…")
        self.update_idletasks()

        try:
            completed = subprocess.run(
                command,
                cwd=Path(__file__).resolve().parent,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            LOGGER.exception("Unable to start indexer: %s", error)
            self.status_var.set("Index update failed.")
            messagebox.showerror("Update Search Index", str(error), parent=self)
            return

        if completed.stdout:
            LOGGER.debug("Indexer stdout:\n%s", completed.stdout.rstrip())
        if completed.stderr:
            LOGGER.debug("Indexer stderr:\n%s", completed.stderr.rstrip())

        if completed.returncode != 0:
            details = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"Indexer exited with code {completed.returncode}."
            )
            self.status_var.set("Index update failed.")
            messagebox.showerror("Update Search Index", details, parent=self)
            return

        self._validate_database()
        self._refresh_all()
        messagebox.showinfo(
            "Update Search Index",
            "Search index updated successfully.",
            parent=self,
        )

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def sort_by_column(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = column in {"date", "messages"}
        LOGGER.debug("Sorting by %s reverse=%s", self.sort_column, self.sort_reverse)
        self._populate_conversation_tree()

    def _sorted_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        key_functions = {
            "date": lambda row: row.get("created_at") or "",
            "title": lambda row: (row.get("title") or "").casefold(),
            "origin": lambda row: (row.get("origin_display") or "").casefold(),
            "projects": lambda row: (row.get("projects_display") or "").casefold(),
            "tags": lambda row: (row.get("tags_display") or "").casefold(),
            "messages": lambda row: int(row.get("message_count") or 0),
        }
        return sorted(rows, key=key_functions[self.sort_column], reverse=self.sort_reverse)

    # ------------------------------------------------------------------
    # Tree navigation and selection
    # ------------------------------------------------------------------

    def _project_tree_selected(self, _event: tk.Event | None = None) -> None:
        if self._suppress_project_selection_event:
            return
        selection = self.project_tree.selection()
        if not selection:
            return

        iid = selection[0]
        value = self.project_iid_to_name.get(iid)
        path = self.project_iid_to_path.get(iid)

        if value == PROJECT_VIEW_ALL:
            self.project_var.set(ALL_VALUE)
            self.project_view = PROJECT_VIEW_ALL
            self.refresh_conversations()
        elif value == PROJECT_VIEW_UNPROJECTED:
            self.project_var.set(ALL_VALUE)
            self.project_view = PROJECT_VIEW_UNPROJECTED
            self.refresh_conversations()
        elif value == PROJECT_VIEW_MULTIPLE:
            self.project_var.set(ALL_VALUE)
            self.project_view = PROJECT_VIEW_MULTIPLE
            self.refresh_conversations()
        elif path:
            # Every visual branch is a valid filter, even when no concrete
            # work_projects row exists exactly at this level.
            self.project_var.set(path)
            self.project_view = PROJECT_VIEW_PROJECT
            self.refresh_conversations()
        else:
            self.status_var.set("Projects — select a branch to filter conversations.")

    def _selected_row(self) -> dict[str, Any] | None:
        selection = self.conversation_tree.selection()
        if not selection:
            return None
        return self.rows_by_iid.get(selection[0])

    def _conversation_selected(self, _event: tk.Event | None = None) -> None:
        row = self._selected_row()
        if not row:
            self._clear_details()
            return
        self._load_details(row["conversation_id"])

    def _load_details(self, conversation_id: str) -> None:
        detail = core.get_conversation(self.database_path, conversation_id)
        if not detail:
            self._clear_details()
            return

        self.detail_title_var.set(detail["title"])
        self.detail_date_var.set((detail.get("created_at") or "—")[:19])
        self.detail_origin_var.set(detail.get("origin_display") or "—")
        self.detail_count_var.set(str(detail.get("message_count", 0)))

        self.detail_project_list.delete(0, "end")
        for project in detail.get("projects", []):
            self.detail_project_list.insert("end", project)

        categories = ", ".join(detail.get("categories", [])) or "—"
        tags = ", ".join(detail.get("tags", [])) or "—"
        self.detail_meta_var.set(f"Categories: {categories}\nTags: {tags}")

        excerpts = core.matching_message_excerpts(
            self.database_path,
            conversation_id,
            self.search_var.get(),
            limit=8,
        )
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        for item in excerpts:
            role = item["author_role"].upper()
            self.preview_text.insert("end", f"Message {item['message_order']} · {role}\n", "heading")
            self.preview_text.insert("end", item["body"] + "\n\n")
        self.preview_text.tag_configure("heading", font=("TkDefaultFont", 9, "bold"))
        self.preview_text.configure(state="disabled")

    def _clear_details(self) -> None:
        self.detail_title_var.set("—")
        self.detail_date_var.set("—")
        self.detail_origin_var.set("—")
        self.detail_count_var.set("—")
        self.detail_project_list.delete(0, "end")
        self.detail_meta_var.set("—")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------

    def open_selected_docx(self) -> None:
        row = self._selected_row()
        if not row:
            return
        try:
            open_with_default_application(row.get("docx_path"))
        except OSError as error:
            messagebox.showerror("Open DOCX", str(error), parent=self)

    def open_selected_in_explorer(self) -> None:
        """Reveal the selected conversation's DOCX in Explorer/Finder."""
        row = self._selected_row()
        if not row:
            return
        try:
            reveal_in_file_manager(row.get("docx_path"))
        except OSError as error:
            messagebox.showerror("Open in Explorer", str(error), parent=self)

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    def new_project(self) -> None:
        name = simpledialog.askstring(
            "New Project",
            "Project name (slashes may be used to create a visual hierarchy):",
            parent=self,
        )
        if not name:
            return
        try:
            created = core.create_project(self.database_path, name)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("New Project", str(error), parent=self)
            return
        self.status_var.set(f"Project created: {created}")
        self._refresh_all()

    def _selected_project_path(self) -> str | None:
        """Return the semantic path of the selected visual project branch."""
        selection = self.project_tree.selection()
        if not selection:
            return None
        return self.project_iid_to_path.get(selection[0])

    def _selected_concrete_project(self) -> str | None:
        selection = self.project_tree.selection()
        if not selection:
            return None
        value = self.project_iid_to_name.get(selection[0])
        if not value or value.startswith("__"):
            return None
        return value

    def add_subproject(self) -> None:
        """Create one child below the selected visual branch."""
        parent_path = self._selected_project_path()
        if parent_path is None:
            messagebox.showinfo(
                "Add Sub-project",
                "Right-click a branch under Projects first.",
                parent=self,
            )
            return

        parent_label = parent_path or "Projects"
        child = simpledialog.askstring(
            "Add Sub-project",
            f"New sub-project under '{parent_label}':",
            parent=self,
        )
        if not child:
            return
        child = child.strip()
        if "/" in child:
            messagebox.showerror(
                "Add Sub-project",
                "Enter only the new sub-project name here, without '/'.",
                parent=self,
            )
            return

        full_name = core.join_project_path(parent_path, child)
        try:
            created = core.create_project(self.database_path, full_name)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Add Sub-project", str(error), parent=self)
            return

        self.project_var.set(created)
        self.project_view = PROJECT_VIEW_PROJECT
        self.status_var.set(f"Sub-project created: {created}")
        self._refresh_all()

    def rename_selected_project(self) -> None:
        branch_path = self._selected_project_path()
        if branch_path is None or not branch_path:
            messagebox.showinfo(
                "Rename Branch",
                "Select a branch under Projects first.",
                parent=self,
            )
            return

        parts = core.project_path_parts(branch_path)
        leaf = parts[-1]
        parent_path = " / ".join(parts[:-1])
        new_leaf = simpledialog.askstring(
            "Rename Branch",
            f"New name for '{leaf}':",
            initialvalue=leaf,
            parent=self,
        )
        if not new_leaf:
            return
        new_leaf = new_leaf.strip()
        if new_leaf == leaf:
            return
        if "/" in new_leaf:
            messagebox.showerror(
                "Rename Branch",
                "Enter only the branch name here, without '/'.",
                parent=self,
            )
            return

        new_path = core.join_project_path(parent_path, new_leaf)
        try:
            renamed_count = core.rename_project_branch(
                self.database_path, branch_path, new_path
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Rename Branch", str(error), parent=self)
            return

        self.project_var.set(new_path)
        self.project_view = PROJECT_VIEW_PROJECT
        self.status_var.set(
            f"Branch renamed: {branch_path} → {new_path} ({renamed_count} project(s))"
        )
        self._refresh_all()

    def delete_selected_project(self) -> None:
        branch_path = self._selected_project_path()
        if branch_path is None or not branch_path:
            messagebox.showinfo(
                "Delete Branch",
                "Select a branch under Projects first.",
                parent=self,
            )
            return

        try:
            stats = core.project_branch_stats(self.database_path, branch_path)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Delete Branch", str(error), parent=self)
            return
        if stats["project_count"] == 0:
            messagebox.showinfo(
                "Delete Branch",
                "This visual branch no longer contains any projects.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Delete Branch",
            f"Delete branch '{branch_path}'?\n\n"
            f"Projects affected: {stats['project_count']}\n"
            f"Conversation assignments removed: {stats['assignment_count']}\n\n"
            "Descendant projects will also be deleted. No archive JSON or DOCX files will be deleted.",
            parent=self,
        ):
            return

        try:
            deleted = core.delete_project_branch(self.database_path, branch_path)
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Delete Branch", str(error), parent=self)
            return

        self.project_var.set(ALL_VALUE)
        self.project_view = PROJECT_VIEW_ALL
        self.status_var.set(
            f"Branch deleted: {deleted['project_count']} project(s), "
            f"{deleted['assignment_count']} assignment(s)."
        )
        self._refresh_all()

    def assign_selected_conversation(self) -> None:
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Assign Project", "Select a conversation first.", parent=self)
            return

        projects = [item["name"] for item in core.list_projects(self.database_path)]
        if not projects:
            name = simpledialog.askstring("Assign Project", "No projects exist. New project name:", parent=self)
            if not name:
                return
            projects = [core.create_project(self.database_path, name)]

        dialog = ProjectPicker(self, projects, title="Assign to Project")
        self.wait_window(dialog)
        if not dialog.result:
            return

        added = core.assign_project(self.database_path, row["conversation_id"], dialog.result)
        self.status_var.set(
            f"{'Assigned' if added else 'Already assigned'}: {row['title']} → {dialog.result}"
        )
        self._refresh_all()
        self._reselect_conversation(row["conversation_id"])

    def remove_selected_project_assignment(self) -> None:
        row = self._selected_row()
        if not row:
            return

        selected = self.detail_project_list.curselection()
        if selected:
            project = self.detail_project_list.get(selected[0])
        else:
            detail = core.get_conversation(self.database_path, row["conversation_id"])
            projects = detail.get("projects", []) if detail else []
            if not projects:
                messagebox.showinfo("Remove Project", "This conversation has no project assignments.", parent=self)
                return
            dialog = ProjectPicker(self, projects, title="Remove Project Assignment")
            self.wait_window(dialog)
            if not dialog.result:
                return
            project = dialog.result

        removed = core.remove_project(self.database_path, row["conversation_id"], project)
        self.status_var.set(
            f"{'Removed' if removed else 'Not assigned'}: {row['title']} ← {project}"
        )
        self._refresh_all()
        self._reselect_conversation(row["conversation_id"])

    # ------------------------------------------------------------------
    # Internal drag-and-drop
    # ------------------------------------------------------------------

    def _project_drag_start(self, event: tk.Event) -> None:
        """Remember a project branch as a possible internal drag source."""
        self.project_drag_source_iid = None
        self.project_drag_source_path = None
        self.project_drag_press_root = None
        self.project_drag_active = False

        iid = self.project_tree.identify_row(event.y)
        if not iid:
            return

        # Do not turn a normal expand/collapse click into a drag candidate.
        element = self.project_tree.identify_element(event.x, event.y)
        if "indicator" in (element or "").casefold():
            return

        path = self.project_iid_to_path.get(iid)
        # None = special views; empty string = synthetic Projects root.
        # Neither can itself be moved.
        if not path:
            return

        self.project_drag_source_iid = iid
        self.project_drag_source_path = path
        self.project_drag_press_root = (event.x_root, event.y_root)
        LOGGER.debug("Project drag candidate: %s (%s)", iid, path)

    def _raw_project_drop_target(self, x_root: int, y_root: int) -> tuple[str | None, str | None]:
        """Return a Treeview item and its semantic path, allowing Projects root."""
        widget = self.winfo_containing(x_root, y_root)
        if widget is not self.project_tree:
            return None, None
        local_y = y_root - self.project_tree.winfo_rooty()
        target_iid = self.project_tree.identify_row(local_y)
        if not target_iid:
            return None, None
        if target_iid not in self.project_iid_to_path:
            return None, None
        return target_iid, self.project_iid_to_path.get(target_iid)

    def _project_drag_target(
        self, x_root: int, y_root: int
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Return (iid, parent_path, destination_path, error_message)."""
        source_path = self.project_drag_source_path
        if not source_path:
            return None, None, None, "No project branch is being dragged."

        target_iid, target_parent = self._raw_project_drop_target(x_root, y_root)
        if not target_iid or target_parent is None:
            return target_iid, target_parent, None, "Drop on Projects or another project branch."

        try:
            destination = core.project_move_destination_path(source_path, target_parent)
        except ValueError as error:
            return target_iid, target_parent, None, str(error)
        return target_iid, target_parent, destination, None

    def _project_drag_motion(self, event: tk.Event) -> None:
        if not self.project_drag_source_path or not self.project_drag_press_root:
            return

        if not self.project_drag_active:
            dx = abs(event.x_root - self.project_drag_press_root[0])
            dy = abs(event.y_root - self.project_drag_press_root[1])
            if max(dx, dy) < 5:
                return
            self.project_drag_active = True
            self._show_drag_popup(
                f"Move branch: {self.project_drag_source_path}",
                event.x_root,
                event.y_root,
            )
            self.status_var.set(
                f"Moving branch: {self.project_drag_source_path} — drop on Projects or another branch"
            )

        if self.drag_popup is not None:
            self.drag_popup.geometry(f"+{event.x_root + 18}+{event.y_root + 18}")

        target_iid, target_parent, destination, error = self._project_drag_target(
            event.x_root, event.y_root
        )
        self._set_drag_target(target_iid if destination else None)

        source_leaf = core.project_path_parts(self.project_drag_source_path)[-1]
        if destination is not None:
            parent_label = target_parent or "Projects"
            self.configure(cursor="hand2")
            if self.drag_popup_label is not None:
                self.drag_popup_label.configure(text=f"{source_leaf}  →  {parent_label}")
            self.status_var.set(f"Move to: {destination}")
        else:
            self.configure(cursor="arrow")
            if self.drag_popup_label is not None:
                self.drag_popup_label.configure(
                    text=f"{source_leaf}  →  {error or 'invalid destination'}"
                )
            if error:
                self.status_var.set(error)

    def _project_drag_end(self, event: tk.Event) -> None:
        source_path = self.project_drag_source_path
        was_active = self.project_drag_active

        target_iid: str | None = None
        target_parent: str | None = None
        destination: str | None = None
        error: str | None = None
        if source_path and was_active:
            target_iid, target_parent, destination, error = self._project_drag_target(
                event.x_root, event.y_root
            )

        self.configure(cursor="arrow")
        self._clear_drag_target()
        self._hide_drag_popup()
        self.project_drag_source_iid = None
        self.project_drag_source_path = None
        self.project_drag_press_root = None
        self.project_drag_active = False

        # A click or tiny pointer movement remains an ordinary Treeview click.
        if not source_path or not was_active:
            return

        if destination is None:
            self.status_var.set(error or "Branch move cancelled.")
            return

        previous_filter = (
            self.project_var.get() if self.project_view == PROJECT_VIEW_PROJECT else ALL_VALUE
        )
        try:
            moved = core.move_project_branch(
                self.database_path, source_path, target_parent or ""
            )
        except (ValueError, OSError, sqlite3.Error) as move_error:
            messagebox.showerror("Move Branch", str(move_error), parent=self)
            self.status_var.set(f"Branch move failed: {move_error}")
            return

        if previous_filter != ALL_VALUE:
            self.project_var.set(
                core.rebase_project_path(previous_filter, source_path, moved["new_path"])
            )
            self.project_view = PROJECT_VIEW_PROJECT

        self._refresh_all()
        self._select_project_tree_path(moved["new_path"])
        self.status_var.set(
            f"Moved: {moved['old_path']} → {moved['new_path']} "
            f"({moved['project_count']} project(s))"
        )

    def _select_project_tree_path(self, path: str) -> None:
        """Select a visual project branch by semantic path without changing filters."""
        wanted = core.normalize_project_path(path).casefold()
        for iid, candidate in self.project_iid_to_path.items():
            if candidate is None:
                continue
            if core.normalize_project_path(candidate).casefold() == wanted:
                self.project_tree.selection_set(iid)
                self.project_tree.focus(iid)
                self.project_tree.see(iid)
                return

    def _drag_start(self, event: tk.Event) -> None:
        row_id = self.conversation_tree.identify_row(event.y)
        if not row_id:
            return

        self.drag_conversation_iid = row_id
        self.conversation_tree.selection_set(row_id)
        self.conversation_tree.focus(row_id)
        row = self.rows_by_iid.get(row_id)
        if row:
            self.status_var.set(
                f"Dragging: {row['title']} — drop on a branch under Projects"
            )
            self._show_drag_popup(row["title"], event.x_root, event.y_root)
        LOGGER.debug("Drag start: %s", row_id)

    def _show_drag_popup(self, title: str, x_root: int, y_root: int) -> None:
        """Show a small floating label so an internal drag is obvious."""
        self._hide_drag_popup()
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        try:
            popup.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = ttk.Label(
            popup,
            text=title,
            padding=(8, 5),
            relief="solid",
        )
        label.pack()
        self.drag_popup = popup
        self.drag_popup_label = label
        popup.geometry(f"+{x_root + 18}+{y_root + 18}")

    def _hide_drag_popup(self) -> None:
        if self.drag_popup is not None:
            try:
                self.drag_popup.destroy()
            except tk.TclError:
                pass
        self.drag_popup = None
        self.drag_popup_label = None

    def _clear_drag_target(self) -> None:
        if self.drag_target_iid and self.project_tree.exists(self.drag_target_iid):
            self.project_tree.item(self.drag_target_iid, tags=())
        self.drag_target_iid = None

    def _set_drag_target(self, target_iid: str | None) -> None:
        if target_iid == self.drag_target_iid:
            return
        self._clear_drag_target()
        if target_iid and self.project_tree.exists(target_iid):
            self.project_tree.item(target_iid, tags=("drop_target",))
            self.drag_target_iid = target_iid

    def _project_drop_target(self, x_root: int, y_root: int) -> tuple[str | None, str | None]:
        """Return (iid, semantic project path) under the pointer."""
        widget = self.winfo_containing(x_root, y_root)
        if widget is not self.project_tree:
            return None, None
        local_y = y_root - self.project_tree.winfo_rooty()
        target_iid = self.project_tree.identify_row(local_y)
        target_path = self.project_iid_to_path.get(target_iid)
        # None = special views; empty string = synthetic Projects root.
        if not target_path:
            return target_iid or None, None
        return target_iid, target_path

    def _drag_motion(self, event: tk.Event) -> None:
        if not self.drag_conversation_iid:
            return

        if self.drag_popup is not None:
            self.drag_popup.geometry(f"+{event.x_root + 18}+{event.y_root + 18}")

        target_iid, target_path = self._project_drop_target(event.x_root, event.y_root)
        self._set_drag_target(target_iid if target_path else None)

        row = self.rows_by_iid.get(self.drag_conversation_iid)
        title = row["title"] if row else "Conversation"
        if target_path:
            self.configure(cursor="hand2")
            if self.drag_popup_label is not None:
                self.drag_popup_label.configure(text=f"{title}  →  {target_path}")
            self.status_var.set(f"Drop target: {target_path}")
        else:
            self.configure(cursor="arrow")
            if self.drag_popup_label is not None:
                self.drag_popup_label.configure(
                    text=f"{title}  →  drop on a project branch"
                )

    def _drag_end(self, event: tk.Event) -> None:
        self.configure(cursor="arrow")
        target_iid, target_path = self._project_drop_target(event.x_root, event.y_root)
        self._clear_drag_target()
        self._hide_drag_popup()

        if not self.drag_conversation_iid:
            return

        row = self.rows_by_iid.get(self.drag_conversation_iid)
        self.drag_conversation_iid = None
        if not row:
            return

        if not target_path:
            self.status_var.set("Drag cancelled — drop on a branch under Projects.")
            return

        try:
            # assign_project creates a concrete work-project automatically when
            # the destination is currently only a visual intermediate branch.
            added = core.assign_project(
                self.database_path, row["conversation_id"], target_path
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            messagebox.showerror("Project assignment", str(error), parent=self)
            return

        self._refresh_all()
        self._reselect_conversation(row["conversation_id"])
        self.status_var.set(
            f"{'Assigned' if added else 'Already assigned'}: {row['title']} → {target_path}"
        )

    def _reselect_conversation(self, conversation_id: str) -> None:
        for iid, row in self.rows_by_iid.items():
            if row["conversation_id"] == conversation_id:
                self.conversation_tree.selection_set(iid)
                self.conversation_tree.focus(iid)
                self.conversation_tree.see(iid)
                self._conversation_selected()
                return

    # ------------------------------------------------------------------
    # Keyword cloud
    # ------------------------------------------------------------------

    def _draw_keyword_cloud(self) -> None:
        canvas = self.keyword_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width() - 16, 180)
        keywords = core.keyword_counts(self.current_rows, limit=45)
        if not keywords:
            canvas.create_text(10, 10, text="No keywords for the current view.", anchor="nw")
            canvas.configure(scrollregion=(0, 0, width, 80))
            return

        max_count = max(count for _, count in keywords)
        x = 8
        y = 12
        line_height = 0

        for word, count in keywords:
            ratio = count / max_count
            font_size = 9 + int(round(10 * math.sqrt(ratio)))
            font = ("TkDefaultFont", font_size, "bold" if ratio > 0.55 else "normal")

            item = canvas.create_text(x, y, text=word, anchor="nw", font=font)
            bbox = canvas.bbox(item)
            if not bbox:
                continue
            item_width = bbox[2] - bbox[0]
            item_height = bbox[3] - bbox[1]

            if x + item_width > width and x > 8:
                x = 8
                y += max(line_height, item_height) + 7
                line_height = 0
                canvas.coords(item, x, y)
                bbox = canvas.bbox(item)
                if bbox:
                    item_width = bbox[2] - bbox[0]
                    item_height = bbox[3] - bbox[1]

            canvas.tag_bind(item, "<Button-1>", lambda _event, value=word: self._keyword_clicked(value))
            canvas.tag_bind(item, "<Enter>", lambda _event: canvas.configure(cursor="hand2"))
            canvas.tag_bind(item, "<Leave>", lambda _event: canvas.configure(cursor=""))

            x += item_width + 12
            line_height = max(line_height, item_height)

        bottom = y + line_height + 16
        canvas.configure(scrollregion=(0, 0, width, bottom))

    def _keyword_clicked(self, keyword: str) -> None:
        self.search_var.set(keyword)
        self.refresh_conversations()

    # ------------------------------------------------------------------
    # Context menu and shutdown
    # ------------------------------------------------------------------

    def _show_project_context_menu(self, event: tk.Event) -> None:
        iid = self.project_tree.identify_row(event.y)
        if not iid:
            return

        self.project_tree.selection_set(iid)
        self.project_tree.focus(iid)
        path = self.project_iid_to_path.get(iid)

        # All conversations / Unprojected / Multiple projects do not represent project branches.
        if path is None:
            return

        # The synthetic Projects root may create a top-level child, but cannot
        # itself be renamed or deleted.
        if path == "":
            self.project_context_menu.entryconfigure("Add Sub-project…", state="normal")
            self.project_context_menu.entryconfigure("Rename…", state="disabled")
            self.project_context_menu.entryconfigure("Delete…", state="disabled")
        else:
            self.project_context_menu.entryconfigure("Add Sub-project…", state="normal")
            self.project_context_menu.entryconfigure("Rename…", state="normal")
            self.project_context_menu.entryconfigure("Delete…", state="normal")

        try:
            self.project_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.project_context_menu.grab_release()

    def _show_context_menu(self, event: tk.Event) -> None:
        row_id = self.conversation_tree.identify_row(event.y)
        if row_id:
            self.conversation_tree.selection_set(row_id)
            self.conversation_tree.focus(row_id)
            self._conversation_selected()
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def _on_close(self) -> None:
        self._save_state()
        self.destroy()


class ProjectPicker(tk.Toplevel):
    def __init__(self, parent: tk.Misc, projects: list[str], *, title: str) -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.title(title)
        self.transient(parent)
        self.resizable(True, True)
        self.geometry("520x420")

        self.filter_var = tk.StringVar()
        ttk.Label(self, text="Filter:").pack(anchor="w", padx=10, pady=(10, 2))
        entry = ttk.Entry(self, textvariable=self.filter_var)
        entry.pack(fill="x", padx=10)

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=8)
        self.listbox = tk.Listbox(frame, exportselection=False)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.projects = sorted(projects, key=str.casefold)
        self._refill()
        self.filter_var.trace_add("write", lambda *_args: self._refill())

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", command=self._accept).pack(side="right", padx=(0, 6))

        self.listbox.bind("<Double-1>", lambda _event: self._accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._accept())
        self.grab_set()
        entry.focus_set()

    def _refill(self) -> None:
        needle = self.filter_var.get().casefold().strip()
        self.listbox.delete(0, "end")
        for project in self.projects:
            if not needle or needle in project.casefold():
                self.listbox.insert("end", project)
        if self.listbox.size():
            self.listbox.selection_set(0)

    def _accept(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        self.result = self.listbox.get(selection[0])
        self.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite index path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=DEBUG,
        help="Enable verbose debug logging.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    arguments = parser.parse_args()
    configure_logging(arguments.debug)
    LOGGER.debug("Arguments: %s", arguments)

    try:
        app = ArchiveBrowser(arguments.database, debug=arguments.debug)
    except (OSError, ValueError, sqlite3.Error) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("ChatGPT Archive Browser", str(error), parent=root)
        root.destroy()
        return 1

    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
