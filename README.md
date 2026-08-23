# GPT Exporter

GPT Exporter is a Windows-oriented tool for preserving, exporting, indexing, searching, and browsing a local ChatGPT conversation archive.

Starting with **v2.8**, the graphical application is the normal entry point. The command-line scripts remain available as implementation layers, diagnostics, and advanced tools.

> [!IMPORTANT]
> GPT Exporter processes private conversation data and temporary browser-session material. Never publish your generated archive, browser bundle, SQLite index, cookies, tokens, account identifiers, or private attachments. See `SECURITY.md`.

## What v2.8 does

GPT Exporter combines four pieces into one workflow:

- **Browser collector** — runs inside your already authenticated ChatGPT browser session and downloads a temporary `chatgpt-archive-source.json` bundle.
- **Archiver / exporter** — preserves cumulative canonical JSON/XZ plus assets and generates readable DOCX exports.
- **Indexer** — maintains a rebuildable SQLite FTS5 search index with provenance and organizational metadata.
- **GPT Exporter GUI** — searches, filters, organizes, opens, and updates the archive without requiring a normal PowerShell workflow.

The v2.8 GUI can copy the browser collector to the clipboard, detect the browser download automatically, run the archive pipeline in the background, update the search index, refresh the Browser, persist workflow logs, and display progress only while it is useful.

## Requirements

- Windows 10 or later is the primary tested platform.
- Python 3.12 or newer.
- A modern browser with Developer Tools; Firefox is the documented collector workflow.
- Dependencies from `requirements.txt` / `pyproject.toml`.

Install dependencies:

```text
py -m pip install -r requirements.txt
```

Optional environment check:

```text
py check_environment.py
```

## Quick start — GUI workflow

Launch GPT Exporter:

```text
py gpt_exporter_gui.py
```

The default archive is:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
```

### Archive new or updated conversations

Use:

```text
Archive → Archive New Conversations…
```

The guided workflow is intentionally simple:

1. Open ChatGPT in your normal browser and make sure you are signed in.
2. Open Developer Tools (`F12`) and select the Console.
3. The collector JavaScript is already placed on the clipboard when the workflow opens; paste and run it.
4. Wait for the browser to download `chatgpt-archive-source.json`.
5. GPT Exporter detects the new bundle automatically and starts the archive workflow.
6. The archive pipeline imports the bundle, preserves assets, regenerates changed exports, updates the SQLite index, and refreshes the GUI.
7. When both the archive and Browser refresh succeed, the progress/log window closes automatically after a short delay.

The collector uses the browser's existing authenticated session. GPT Exporter does not ask Python to store ChatGPT credentials.

Useful Archive-menu maintenance commands remain available:

- **Copy Collector JavaScript** — copy `collect_chatgpt_archive.js` to the clipboard again.
- **Show Collector JavaScript in Explorer** — reveal the collector file for inspection or drag-and-drop workflows.
- **Process Downloaded Bundle…** — manually process an already downloaded bundle.
- **Update Search Index** — run incremental indexing manually.
- **Open Archive Folder** — open the active archive directory.
- **Show Last Archive Log** — open the latest persistent archive-workflow log.

## Persistent workflow logs

Every archive run is logged under the active archive's `reports` directory:

```text
reports\archive-workflow-YYYY-MM-DD_HH-MM-SS.log
reports\archive-workflow-latest.log
```

The timestamped file preserves the streamed archive output for that run. `archive-workflow-latest.log` is refreshed after every completed run, including failures.

A successful run closes the progress window automatically only after the Browser has also refreshed successfully. Archive failures or Browser-refresh failures keep the window open so the diagnostic output remains visible.

## Search and organization

The main window provides:

- SQLite FTS5 full-text search;
- origin, project, tag, and category filters;
- sortable conversation lists;
- hierarchical work projects;
- drag-and-drop conversation assignment to projects;
- drag-and-drop project-branch movement;
- conversation details and matching-message previews;
- direct DOCX opening and reveal-in-file-manager actions;
- a lightweight keyword cloud.

Browser-managed projects, categories, and tags live in the SQLite index. Incremental re-indexing preserves this organizational metadata.

## What happens during an archive run

The GUI delegates to the existing tested command-line engines instead of duplicating archive logic. The canonical workflow is:

```text
1/5 - Import browser archive bundle
2/5 - Inventory media references
3/5 - Build asset manifest
4/5 - Export new or larger conversations
5/5 - Update archive search index
```

A successful run is cumulative and non-destructive. The temporary browser bundle is consumed only after the archive workflow succeeds.

## Archive model and preservation invariants

The project deliberately follows conservative preservation rules:

1. Canonical durable data is `downloads\*.json.xz + assets\*`.
2. DOCX, Markdown, SQLite indexes, manifests, reports, and workflow logs are derived/rebuildable.
3. Normal archiving is cumulative and non-destructive.
4. Existing conversations and assets are never pruned merely because a later browser bundle omits them.
5. Asset collection is deliberately broad; over-collection is safer than silently losing recoverable files.
6. ChatGPT `file_id` values embedded in archived filenames are stable local join keys.
7. Unsupported raster formats may be normalized in memory for DOCX embedding, but original archived assets are not rewritten for compatibility.
8. Ambiguous historical `sandbox:/mnt/data/...` links are never resolved by guessing.
9. Missing visible attachments are represented explicitly rather than silently substituted.
10. Changes affecting canonical data, deletion policy, collection breadth, visible-role semantics, or local-link semantics require explicit documentation and migration/rollback consideration.

`FROZEN_VERSION.md` records the historical v2.7 preservation baseline. v2.8 keeps those archive invariants while moving normal operation into the GUI.

## Advanced / command-line use

The GUI is the recommended entry point, but the underlying tools remain usable directly.

Run the cumulative archive workflow:

```text
py archive_chats.py
```

Rebuild derived DOCX files from the existing local JSON/XZ archive:

```text
py archive_chats.py --convert-only
```

Build or update the SQLite search index:

```text
py index_chatgpt_archive.py index
```

Run the older Browser-only entry point:

```text
py archive_browser.py
```

Generate persistent Markdown explicitly:

```text
py export_all.py --markdown-only --overwrite-all
```

Destructive archive reset, intended only for deliberate recovery/testing:

```text
py archive_chats.py --fresh
```

`--fresh` deletes the generated local archive tree before importing the current bundle. It is **not** intended for routine use.

## Main files

| File | Purpose |
|---|---|
| `gpt_exporter_gui.py` | Main v2.8 graphical application |
| `archive_gui_workflow.py` | Guided collection/archive workflow, persistent logs, and background process UI |
| `collect_chatgpt_archive.js` | Browser-side collector for conversations and browser-accessible assets |
| `archive_chats.py` | Canonical cumulative archive orchestration workflow |
| `import_browser_bundle.py` | Imports the temporary browser bundle into the persistent archive |
| `inventory_media.py` | Inventories media references |
| `build_asset_manifest.py` | Builds cumulative asset-reference diagnostics |
| `build_browser_asset_cache_seed.py` | Seeds the optional browser asset cache from an existing local report |
| `export_all.py` | Coordinates Markdown/DOCX export and cumulative asset audit |
| `export_markdown.py` | Converts archived conversation JSON/XZ to Markdown |
| `export_docx.py` | Converts Markdown to DOCX and preserves local asset links |
| `audit_asset_references.py` | Audits physical asset/reference consistency without deleting data |
| `index_chatgpt_archive.py` | SQLite FTS5 indexer and organization CLI |
| `archive_core.py` | Shared data/query core for the Archive Browser |
| `archive_browser.py` | Browser/organizer base used by the v2.8 GUI |
| `check_environment.py` | Checks runtime dependencies and active pipeline files |

## Privacy

Generated archive data is intentionally excluded by `.gitignore`. In particular, do not commit:

- `chatgpt-archive-source.json`;
- conversation JSON/XZ files;
- downloaded assets or attachments;
- generated DOCX/Markdown containing private conversations;
- `conversations-index.sqlite` or its WAL/SHM files;
- browser cookies, access tokens, account IDs, or authorization headers.

See `SECURITY.md` for reporting guidance.

## Development

Run the test suite with:

```text
py -m unittest discover -s tests -v
```

Compile-check the Python sources:

```text
py -m compileall -q .
```

GitHub Actions validates Python 3.12 and 3.13 on Windows. `main` is protected and release changes are merged through pull requests with required status checks.

See `CONTRIBUTING.md` before changing archive semantics.

## Documentation and release history

- `docs/V2_8_GUI_WORKFLOW.md` — v2.8 GUI design and workflow architecture.
- `docs/RELEASE_NOTES_V2.8.md` — v2.8 release summary and validation notes.
- `CHANGELOG.md` — detailed historical release lineage.
- `FROZEN_VERSION.md` — historical v2.7 validation and preservation baseline.
- `SOURCE_SHA256SUMS.txt` — original frozen v2.7 package hashes; retained as historical evidence and not intended to match later Git checkouts.

## License

GPT Exporter is free software licensed under **GNU GPL v3 or later (`GPL-3.0-or-later`)**. See `LICENSE`.
