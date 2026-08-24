# GPT Exporter Release History

## v2.9 — Windows executable distribution — 2026-08-24

GPT Exporter v2.9 turns the proven v2.8 Python application into a package-oriented Windows application that can be distributed as a self-contained executable without requiring the user to install Python.

Highlights:

- Added v2.8 characterization fixtures and regression tests before refactoring.
- Introduced the reusable `gpt_exporter` package and explicit `ArchivePaths` configuration.
- Moved media inventory, asset manifest, asset audit, Markdown export, DOCX export, incremental indexing, browser-bundle import, and complete archive orchestration behind import-safe library APIs.
- Replaced dynamic script loading and temporary `sys.argv` mutation in the batch exporter with direct library calls.
- Replaced the GUI-to-archive Python subprocess with an in-process worker thread and queue-based Tkinter progress handling.
- Closed the reusable core inside `gpt_exporter/` so it no longer depends on repository-root implementation modules.
- Converted historical command-line implementations into thin compatibility wrappers.
- Packaged the collector JavaScript, user guide, and release history as application resources.
- Added central application version metadata, `--version`, a Markdown documentation viewer, and an About dialog.
- Added reproducible PyInstaller `onedir` packaging for Windows with Python 3.13.
- Added a true Windows GUI/windowed executable with PE File/Product version metadata generated from the central version source.
- Added GitHub Actions validation for Python 3.12 and 3.13 plus a dedicated Windows packaging workflow.
- Added CI verification of the Windows GUI subsystem, version metadata, packaged resources, and release artifact contents.

The durable archive model and v2.8 user-visible archive semantics remain intentionally unchanged. Canonical archive data is still cumulative `downloads/*.json.xz + assets/*`; DOCX, Markdown, SQLite indexes, manifests, reports, and logs remain derived/rebuildable.

## v2.8 — GUI-first archive workflow — 2026-08-23

v2.8 made the graphical application the normal day-to-day entry point.

Highlights:

- Added the **Archive** menu and guided **Archive New Conversations…** workflow.
- Copied the browser collector to the clipboard automatically.
- Detected newly downloaded `chatgpt-archive-source.json` bundles automatically.
- Ran the tested archive pipeline in the background and refreshed the Browser after success.
- Added persistent timestamped workflow logs plus `archive-workflow-latest.log`.
- Added **Archive → Show Last Archive Log**.
- Closed the progress window automatically only after both archive processing and Browser refresh succeeded.
- Preserved cumulative `downloads/*.json.xz + assets/*` as the durable archive source.
- Preserved Browser-managed projects, categories, and tags during incremental indexing.
- Kept the integrated archive workflow intentionally limited to `%USERPROFILE%\Documents\ChatGPT Archive`.

## v2.7 — Frozen preservation baseline — 2026-08-17

v2.7 froze the preservation and asset-handling baseline used by later releases.

Highlights:

- Rebuilt the archived conversation corpus successfully under the frozen release candidate.
- Added cumulative asset-reference auditing and detailed duplicate/provenance diagnostics.
- Preserved generated images, visible attachment provenance, dictation audio references, and conservative local-link handling.
- Kept duplicate physical assets when historical provenance could differ even if bytes were identical.
- Refused to guess ambiguous historical sandbox-link targets.
- Kept all asset auditing diagnostic and non-destructive.

## v2.6

- Added visible DOCX provenance for archived assets.
- Added local links for archived attachments using Windows-compatible relative paths.
- Preserved missing or ambiguous sandbox targets as visible non-clickable text rather than guessed links.

## v2.4

- Added robust DOCX image embedding with an in-memory Pillow fallback for formats or metadata rejected by `python-docx`.
- Preserved original archived image bytes unchanged.

## v2.3

- Added physical-archive fallback discovery when the derived asset registry did not contain older archived assets.
- Established that the asset registry is a rebuildable cache/report rather than the archive source of truth.

## v2

v2 established the cumulative archive architecture still used today:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
├── *.docx
├── downloads\
│   └── *.json.xz
├── assets\
└── reports\
```

Core rules include cumulative conversation preservation, XZ-compressed canonical JSON, non-destructive asset storage, and rebuildable derived outputs.

For the exhaustive historical release record, see the repository `CHANGELOG.md`.
