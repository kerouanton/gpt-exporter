# Multi Social Network Explorer (MSNE) User Guide

Multi Social Network Explorer (MSNE) preserves, exports, indexes, searches, and organizes local conversation archives from independently packaged providers such as ChatGPT and Discord.

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

Projects are local organizational metadata stored in the rebuildable SQLite index. They are independent from provider-native project or grouping concepts.

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

DOCX files are derived outputs. Durable archive data remains provider-owned canonical conversation data plus archived assets.

## Archiving new or updated conversations

Use the active provider's archive action from the **Archive** menu. The shared workflow window handles collector guidance, download detection, background processing, progress, persistent logs, and Browser refresh; each provider supplies its own service-specific collection and archive operations.

For ChatGPT, the guided workflow is:

1. MSNE opens the archive workflow window and copies the collector JavaScript to the clipboard.
2. Open ChatGPT in your normal authenticated browser session.
3. Open Developer Tools and select the Console.
4. Paste and run the collector JavaScript.
5. Wait for the browser to download `chatgpt-archive-source.json`.
6. MSNE detects the new non-empty bundle.
7. The archive pipeline imports the bundle, inventories media, builds asset diagnostics, exports changed conversations, and updates the search index.
8. The Browser refreshes after success.

The progress window closes automatically only when both the archive pipeline and Browser refresh succeed. A failure keeps the window visible for diagnosis.

## Archive menu

Available commands depend on the active provider. Common maintenance actions include updating the search index, opening the active archive folder, and viewing the latest archive log. Provider-specific commands may open the remote service, copy or reveal collector JavaScript, process an already-downloaded bundle, regenerate derived exports, or perform explicitly guarded remote maintenance operations.

## Persistent logs

Each archive run writes a timestamped log below the active workspace `reports` directory and refreshes a stable latest-log file.

Typical names are:

```text
reports\archive-workflow-YYYY-MM-DD_HH-MM-SS.log
reports\archive-workflow-latest.log
```

Use the provider's latest-log command when an archive operation needs diagnosis.

## Preservation model

MSNE follows conservative archive rules:

- canonical durable conversation data is retained by the active provider;
- archived assets are preserved under the provider workspace;
- DOCX, Markdown, SQLite indexes, manifests, reports, and workflow logs are derived or rebuildable unless explicitly documented otherwise;
- a partial recapture must not silently erase known history;
- ambiguous asset mappings are not guessed;
- provider-specific destructive remote actions must not silently damage the local canonical archive.

## Default archive locations

Current default provider workspaces include:

```text
%USERPROFILE%\Documents\ChatGPT Archive
%USERPROFILE%\Documents\Discord Archive
```

These provider archive names are historical/data-domain identities and are not automatically renamed to MSNE directories.

## Privacy

Local archives may contain private conversations, attachments, generated documents, and temporary browser-session material.

Do not publish archive data, browser bundles, SQLite databases, access tokens, account identifiers, or private attachments.

## Troubleshooting

If the Browser does not show a newly archived conversation, first inspect the latest archive log and verify whether the provider pipeline completed successfully.

If the index is stale while the durable archive files are correct, use the search-index update action.

If a generated DOCX is missing or outdated, inspect the relevant provider workflow log and regeneration/repair commands.

For release-specific behavior and known limitations, open **Help → Release History…**.

## Version information

Use **Help → About Multi Social Network Explorer…** to see the running application version.

From a terminal, the historical GUI entry point remains supported during the compatibility migration:

```text
py gpt_exporter_gui.py --version
```
