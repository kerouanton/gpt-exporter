# v2.8 GUI workflow

## Goal

GPT Exporter v2.8 makes the Archive Browser the normal entry point for day-to-day use.

Command-line scripts remain available as stable implementation layers and for diagnostics, but a normal archive/update cycle must not require the user to open PowerShell or remember individual commands.

## Design principles

- Keep `downloads/*.json.xz` and `assets/*` as canonical archive data.
- Keep `archive_chats.py` as the canonical archive orchestration engine.
- Keep `index_chatgpt_archive.py` as the canonical SQLite indexer.
- The GUI invokes those engines rather than reimplementing their logic.
- Normal archive updates are cumulative and non-destructive.
- Incremental indexing preserves Browser-managed projects, categories, and tags.
- Long-running archive work must not freeze the Tkinter user interface.
- The GUI must expose enough progress and log output to diagnose failures without requiring a terminal.

## Proposed Archive menu

```text
Archive
├─ Archive New Conversations…
├─ Open ChatGPT
├─ Copy Collector JavaScript
├─ Show Collector JavaScript in Explorer
├─ Process Downloaded Bundle…
├─ ─────────────────────────────
├─ Update Search Index
├─ Open Archive Folder
└─ Show Last Archive Log…
```

`Update Search Index` remains a manual maintenance command. A successful normal archive run updates the index automatically and refreshes the Browser.

## Guided archive workflow

### Step 1 — Prepare collection

The workflow dialog explains that collection runs inside the authenticated ChatGPT browser session.

Actions:

- **Open ChatGPT** opens `https://chatgpt.com/` in the default browser.
- **Copy Collector JavaScript** reads `collect_chatgpt_archive.js` from the application directory and places its complete contents on the clipboard.
- **Show Collector in Explorer** reveals the JavaScript file in the system file manager for users who prefer to work with the file directly.

The GUI never stores or requests ChatGPT credentials.

### Step 2 — Run collector in the browser

The dialog gives concise instructions for opening Developer Tools, opening the Console, pasting/running the collector, and waiting for the browser download to finish.

The collector continues to create:

```text
chatgpt-archive-source.json
```

### Step 3 — Detect the downloaded bundle

The GUI checks the same Windows Downloads candidates already used by `archive_chats.py` and shows the newest valid `chatgpt-archive-source.json` when one appears.

The user can either:

- continue with the automatically detected bundle; or
- choose a bundle manually when required.

No archive data is modified at this stage.

### Step 4 — Run the archive workflow

The GUI launches `archive_chats.py` as a child process and displays its combined output in a progress/log window.

The canonical workflow remains:

```text
1/5 Import browser archive bundle
2/5 Inventory media references
3/5 Build asset manifest
4/5 Export new or larger conversations
5/5 Update archive search index
```

The GUI must not duplicate these operations internally.

### Step 5 — Refresh Browser

After a successful child process exit:

1. validate the SQLite database;
2. refresh filter values;
3. rebuild the project tree;
4. refresh conversation results;
5. report the updated conversation count.

Failures leave the GUI open, preserve the log, and do not claim that the archive is current.

## Interaction details

### Clipboard

Use Tkinter's own clipboard methods so no additional dependency is required.

The complete collector source is copied verbatim from the repository file.

### Explorer integration

Reuse the existing platform file-reveal helper. On Windows this should select `collect_chatgpt_archive.js` in Explorer.

### Long-running child process

`archive_chats.py` must run without blocking Tk's event loop. The GUI should stream or periodically drain process output into a log widget while the process is running.

The first implementation may use a background reader thread plus a queue, with all Tk widget updates performed through `after()` on the Tk thread.

### Manual bundle processing

`Process Downloaded Bundle…` provides a direct entry point for users who already ran the collector. It should use the normal archive workflow and not create a second import implementation.

### Logs

The guided workflow should retain the last run's text in memory and optionally write a derived log under the archive `reports` directory. Logs are diagnostic/derived data and are not canonical archive data.

## Implementation stages

### Stage 1 — GUI archive controls

- Add the `Archive` menu.
- Add Open ChatGPT.
- Add Copy Collector JavaScript.
- Add Show Collector JavaScript in Explorer.
- Move/expose Update Search Index under the Archive menu.
- Add Open Archive Folder.
- Add focused helper tests.

### Stage 2 — Guided workflow and bundle detection

- Add the workflow dialog.
- Detect the newest valid bundle in Windows Downloads.
- Allow manual bundle selection.
- Make the collection instructions self-contained.

### Stage 3 — Background archive execution

- Launch `archive_chats.py` from the GUI.
- Stream progress/log output without freezing the GUI.
- Refresh the Browser automatically after success.
- Preserve useful error output after failure.

### Stage 4 — Polish

- Improve status/progress presentation.
- Add last-run summary.
- Update README and screenshots/documentation.
- Complete end-to-end Windows smoke testing before tagging v2.8.

## Out of scope for the first v2.8 pass

- Browser automation that injects JavaScript into ChatGPT automatically.
- Capturing or storing ChatGPT credentials/session tokens in Python.
- Reimplementing archive/index logic inside the GUI.
- Removing the command-line interfaces.

These exclusions keep the browser authentication boundary explicit and preserve the existing tested archive architecture.
