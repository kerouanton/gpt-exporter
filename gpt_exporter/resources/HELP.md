# GPT Exporter User Guide

GPT Exporter preserves, exports, indexes, searches, and organizes a local ChatGPT conversation archive.

The normal entry point is the graphical application. The command-line tools remain available for diagnostics and advanced workflows.

## Main window

The main window is divided into three working areas:

- **Projects** on the left, for organizing conversations into your own work hierarchy.
- **Conversation list** in the center, filtered by search text, origin, tag, category, and project.
- **Conversation details** on the right, with metadata, project assignments, categories/tags, and a message preview.

The status bar at the bottom reports the active selection and operation status.

## Search and filters

Type search terms in the **Search** field to query the SQLite FTS5 index.

Use the **Origin**, **Tag**, and **Category** selectors to narrow the result set. The **Recursive** option controls whether a selected project includes conversations assigned to descendant projects.

Use **View → Clear Filters** to return to an unfiltered view.

Use **Help → Search Syntax…** for the dedicated search-expression reference.

## Projects

Projects are local organizational metadata stored in the rebuildable SQLite index. They are independent from native ChatGPT Project provenance.

You can:

- create a project;
- add sub-projects;
- rename or delete project branches;
- assign a selected conversation to one or more work projects;
- remove a project assignment;
- drag conversations or project branches where supported by the current Browser view.

Incremental archive indexing preserves project, category, and tag assignments.

## Opening conversation exports

Select a conversation, then use **Open DOCX** to open its generated document with the default Windows application.

Use **Open in Explorer** to reveal the corresponding export in Windows Explorer.

DOCX files are derived outputs. The durable archive source remains the cumulative conversation JSON/XZ plus archived assets.

## Archiving new or updated conversations

Use:

**Archive → Archive New Conversations…**

The guided workflow performs the normal collection and archive update:

1. GPT Exporter opens the archive workflow window and copies the collector JavaScript to the clipboard.
2. Open ChatGPT in your normal authenticated browser session.
3. Open Developer Tools and select the Console.
4. Paste and run the collector JavaScript.
5. Wait for the browser to download `chatgpt-archive-source.json`.
6. GPT Exporter detects the new non-empty bundle.
7. The archive pipeline imports the bundle, inventories media, builds asset diagnostics, exports changed conversations, and updates the search index.
8. The Browser refreshes after success.

The progress window closes automatically only when both the archive pipeline and Browser refresh succeed. A failure keeps the window visible for diagnosis.

## Archive menu

Useful maintenance commands include:

- **Open ChatGPT** — open ChatGPT in the default browser.
- **Copy Collector JavaScript** — copy the collector again.
- **Show Collector JavaScript in Explorer** — reveal the collector source file.
- **Process Downloaded Bundle…** — process an already downloaded browser bundle manually.
- **Update Search Index** — perform an incremental index update.
- **Open Archive Folder** — open the active archive directory.
- **Show Last Archive Log** — open the latest persistent workflow log.

## Persistent logs

Each archive run writes a timestamped log below the archive `reports` directory and refreshes a stable latest-log file.

Typical names are:

```text
reports\archive-workflow-YYYY-MM-DD_HH-MM-SS.log
reports\archive-workflow-latest.log
```

Use **Archive → Show Last Archive Log** when an archive operation needs diagnosis.

## Preservation model

GPT Exporter follows conservative archive rules:

- canonical durable conversation data is stored below `downloads` as compressed JSON/XZ;
- archived assets are preserved below `assets`;
- DOCX, Markdown, SQLite indexes, manifests, reports, and workflow logs are derived or rebuildable;
- a shorter or equal incoming conversation snapshot never replaces a larger stored snapshot;
- normal incremental archiving does not prune older conversations merely because they are absent from a later browser bundle;
- duplicate physical assets are not automatically deduplicated because identical bytes may represent different historical provenance.

## Default archive location

The integrated Windows workflow currently targets:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

The Browser may open another SQLite database for inspection, but the integrated archive-update workflow deliberately refuses to write through a Browser instance pointed at a different archive database.

## Privacy

The local archive may contain private conversations, attachments, generated documents, and temporary browser-session material.

Do not publish archive data, browser bundles, SQLite databases, access tokens, account identifiers, or private attachments.

## Troubleshooting

If the Browser does not show a newly archived conversation, first use **Archive → Show Last Archive Log** and verify whether the archive pipeline completed successfully.

If the index is stale while the durable archive files are correct, use **Archive → Update Search Index**.

If a generated DOCX is missing or outdated, verify that the conversation was part of the latest current batch and inspect the workflow log for exporter warnings or errors.

For release-specific behavior and known limitations, open **Help → Release History…**.

## Version information

Use **Help → About GPT Exporter…** to see the running application version.

From a terminal, the GUI entry point also supports:

```text
py gpt_exporter_gui.py --version
```
