# GPT Exporter Release History

## v2.9 development line

The v2.9 line focuses on turning the proven v2.8 Python application into a clean, package-oriented Windows application that can be distributed as an executable without requiring the user to install Python.

### Architecture work completed before packaging

- Added v2.8 characterization fixtures and regression tests before refactoring.
- Introduced the reusable `gpt_exporter` package and explicit `ArchivePaths` configuration.
- Moved media inventory, asset manifest, and asset audit logic behind import-safe library APIs.
- Added explicit Markdown and DOCX export APIs while preserving v2.8 output semantics.
- Replaced dynamic script loading and temporary `sys.argv` mutation in the batch exporter with direct library calls.
- Moved incremental SQLite indexing behind a reusable API with explicit database lifetime management.
- Preserved work-project, category, and tag assignments across incremental re-indexing.
- Moved browser-bundle import and the complete archive pipeline behind in-process APIs.
- Replaced the GUI-to-archive Python subprocess with a worker thread and queue-based Tkinter progress handling.
- Closed the reusable core inside `gpt_exporter/` so it no longer depends on repository-root implementation modules.
- Converted the historical importer, Markdown exporter, DOCX exporter, and indexer scripts into thin compatibility wrappers.
- Packaged the browser collector JavaScript as an application resource.
- Added local and CI coverage for package closure, wrapper compatibility, and Windows newline materialization.

### Current development UI work

- Central application version metadata.
- `--version` support on the graphical entry point.
- Help-menu access to a packaged user guide and release history.
- Reusable Markdown documentation viewer.
- About dialog with version, license identifier, documentation shortcuts, and repository access.

The durable archive model and v2.8 user-visible archive semantics remain intentionally unchanged while this work proceeds.

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
