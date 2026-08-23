# GPT Exporter v2.8 release notes

Release date: 2026-08-23

## Summary

GPT Exporter v2.8 makes the graphical application the normal entry point for day-to-day archive use.

The v2.7 preservation model remains unchanged: canonical data is still stored as cumulative `downloads/*.json.xz` plus `assets/*`, while DOCX, Markdown, reports, manifests, and the SQLite search index remain derived/rebuildable data.

The major v2.8 change is workflow integration. A normal archive/update cycle no longer requires the user to remember or manually sequence command-line tools.

## Highlights

- New `gpt_exporter_gui.py` main application.
- New **Archive** menu integrated with the existing search/browser interface.
- Guided **Archive New Conversations…** workflow.
- Collector JavaScript is copied automatically to the clipboard when the guided workflow opens.
- **Open ChatGPT** action opens the authenticated browser workflow.
- **Show Collector JavaScript in Explorer** remains available from the Archive menu for inspection or alternate workflows.
- Automatic monitoring for a newly downloaded `chatgpt-archive-source.json`.
- A pre-existing bundle is ignored for automatic triggering; only a new or replaced download starts the guided archive run.
- Automatic launch of the canonical `archive_chats.py` pipeline as soon as the new bundle is detected.
- Background process execution keeps the Tkinter GUI responsive.
- Live archive output is shown in a dedicated progress/log window.
- Every archive run is also persisted under `reports/` as a timestamped UTF-8 log, with `archive-workflow-latest.log` updated to the most recent run.
- **Show Last Archive Log** opens the most recent persistent workflow log from the Archive menu.
- After a completely successful archive and Browser refresh, the progress/log window closes automatically after a short delay.
- Failed archive runs or Browser-refresh failures keep the progress/log window open for diagnosis.
- Archive indexing remains the final canonical pipeline step.
- The Browser validates and refreshes the SQLite index automatically after a successful archive run.
- Manual **Update Search Index**, **Process Downloaded Bundle…**, **Open Archive Folder**, and collector utilities remain available for maintenance.

## Archive workflow

The integrated workflow remains intentionally layered rather than duplicating archive logic inside the GUI:

```text
Browser collector
    ↓
chatgpt-archive-source.json
    ↓
archive_chats.py
    ↓
1/5 Import browser archive bundle
2/5 Inventory media references
3/5 Build asset manifest
4/5 Export new or larger conversations
5/5 Update archive search index
    ↓
GUI refresh
```

The Python application never requests or stores ChatGPT credentials. Collection continues to run inside the user's already authenticated browser session.

## Persistent workflow logs

The live Archive Workflow window is diagnostic output, but v2.8 also keeps a persistent copy under the active archive's `reports` directory:

```text
reports/
├─ archive-workflow-YYYY-MM-DD_HH-MM-SS.log
└─ archive-workflow-latest.log
```

The timestamped log preserves the complete streamed output for that run. `archive-workflow-latest.log` is refreshed after each completed run, including failures, and can be opened through **Archive → Show Last Archive Log**.

Persistent logs are derived diagnostic data. They do not replace or modify canonical conversation JSON/XZ or archived assets.

## Search and organization

v2.8 retains the Archive Browser features introduced during the v2.7 repository work:

- SQLite FTS5 full-text search;
- origin, project, tag, and category filters;
- hierarchical work projects;
- drag-and-drop conversation assignment;
- project-branch management;
- conversation/message preview;
- DOCX open/reveal actions;
- incremental indexing that preserves Browser-managed organization metadata.

## Validation

The v2.8 development branch is validated by GitHub Actions on Windows with Python 3.12 and 3.13. The workflow compiles the Python sources, runs the unit-test suite, and validates project metadata.

A real Windows end-to-end smoke test validated the user-facing workflow:

1. start the guided workflow from the GUI;
2. run the copied collector in ChatGPT;
3. allow the GUI to detect the newly downloaded bundle automatically;
4. run the complete archive pipeline without manual command-line intervention;
5. update the SQLite index;
6. refresh the Browser;
7. verify that a newly archived conversation appears in the GUI automatically;
8. open the DOCX for the current conversation and verify that it contains the latest archived content.

The persistent-log and auto-close behavior is also covered by focused helper tests: auto-close is permitted only when both the archive process and Browser refresh succeed.

## Final release acceptance

Immediately before tagging v2.8, the final Windows build was smoke-tested again with a fresh conversation. The new conversation appeared automatically in the Browser, the generated DOCX was current, the timestamped and latest workflow logs were created and accessible from the Archive menu, and the Archive Workflow window closed automatically after a successful run. This final acceptance test passed without requiring manual index refresh or a terminal-driven archive step.

## Compatibility and preservation

v2.8 does not change the durable archive source-of-truth model documented by the frozen v2.7 baseline.

The following invariants remain in force:

- normal updates are cumulative and non-destructive;
- older conversations are not deleted because a later bundle omits them;
- assets are not pruned merely because later bundles no longer reference them;
- source assets are not rewritten for DOCX compatibility;
- ambiguous historical local links are not guessed;
- the SQLite index is derived and rebuildable;
- Browser-managed organizational metadata survives incremental indexing.

## Known limitation

The first v2.8 guided archive workflow intentionally targets the default archive location:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

The Browser can still be launched against another SQLite database, but the integrated archive workflow refuses to write through that non-default Browser instance rather than risk updating the wrong archive.

## Upgrade from v2.7

No canonical archive migration is required.

After updating the source checkout and dependencies, launch:

```text
py gpt_exporter_gui.py
```

Existing v2.7 archive data and Browser organization remain usable. The GUI's normal archive workflow updates the search index automatically.

## License

GPT Exporter v2.8 is licensed under GNU GPL v3 or later (`GPL-3.0-or-later`).
