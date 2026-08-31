# GPT Exporter

GPT Exporter is a Windows-oriented local archiver, exporter, indexer and browser
for conversation archives. The current architecture separates a common exporter
CORE from source-specific providers. ChatGPT is the validated reference provider.

> [!IMPORTANT]
> GPT Exporter processes private conversation data and temporary browser-session
> material. Never publish generated archives, source bundles, SQLite indexes,
> cookies, tokens, account identifiers or private attachments. See `SECURITY.md`.

## Current architecture

The application operates on a selected **Workspace**. A workspace binds one
provider to one archive root/database. The GUI uses `WorkspaceWorkflow` as its
single runtime context, so switching workspace changes provider, archive root,
SQLite database, collector/source-bundle lookup, archive execution and index
update together.

Source-specific code belongs to the provider. Shared behavior belongs to CORE:

- GUI and workspace/provider management;
- archive filesystem layout;
- normalized conversation model;
- Markdown/DOCX output;
- SQLite/FTS search index;
- Projects, Tags and Categories;
- filters, previews and keyword cloud;
- task progress/logging and common diagnostics.

The ChatGPT production path has been validated against the historical exporter
with zero differences on the final real-archive compatibility gate. See
`docs/EXPORTER_CORE_CHATGPT_VALIDATION.md`.

## Requirements

- Windows 10 or later is the primary tested platform.
- Python 3.12 or newer for source execution.
- A modern browser with Developer Tools for browser-side collection.
- Dependencies from `requirements.txt` / `pyproject.toml`.

Install dependencies:

```text
py -m pip install -r requirements.txt
```

Optional environment check:

```text
py check_environment.py
```

## Quick start

Launch the GUI:

```text
py gpt_exporter_gui.py
```

The default ChatGPT workspace uses:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
```

Additional workspaces can be created through:

```text
Workspaces -> Manage Workspaces...
```

Multiple workspaces may use the same provider while keeping independent archive
roots and SQLite databases.

## Archive new or updated ChatGPT conversations

Use:

```text
Archive -> Archive New Conversations...
```

The guided workflow:

1. opens/copies the provider collector workflow;
2. waits for `chatgpt-archive-source.json` in the normal Downloads locations;
3. imports the provider-native bundle into the cumulative archive;
4. preserves canonical conversation JSON/XZ and assets;
5. generates changed Markdown/DOCX through CORE;
6. updates the CORE SQLite/FTS index;
7. refreshes the Browser after success.

The normal five visible pipeline stages remain:

```text
1/5 - Import ChatGPT archive bundle
2/5 - Inventory media references
3/5 - Build asset manifest
4/5 - Export new or larger conversations
5/5 - Update archive search index
```

Stages 4 and 5 are authoritative normalized CORE stages.

## Archive menu

Useful maintenance actions include:

- **Open ChatGPT** — open the current provider website;
- **Copy Collector JavaScript** — copy the packaged collector;
- **Show Collector JavaScript in Explorer** — reveal the collector file;
- **Process Downloaded Bundle...** — manually process a downloaded provider bundle;
- **Update Search Index** — run the current workspace's CORE incremental indexer;
- **Open Archive Folder** — open the current workspace archive root;
- **Show Last Archive Log** — open the latest persistent archive log.

Provider-facing labels and actions are derived from the selected workspace rather
than hard-coded into a second provider-specific GUI.

## Search and organization

The common Browser provides:

- SQLite FTS5 full-text search;
- origin, project, tag and category filters;
- sortable conversation lists;
- hierarchical projects;
- drag-and-drop conversation/project organization;
- matching-message previews;
- DOCX opening and reveal-in-file-manager actions;
- keyword cloud.

Projects, Categories and Tags live in the SQLite index and survive incremental
reindexing.

## Archive model and preservation invariants

The preservation model remains conservative:

1. `downloads/*.json.xz + assets/*` are canonical durable data.
2. DOCX, Markdown, SQLite indexes, manifests, reports and logs are derived/rebuildable.
3. Normal archiving is cumulative and non-destructive.
4. A conversation or asset omitted from a later bundle is not implicitly deleted.
5. Asset collection remains deliberately broad.
6. Stable provider file IDs are used for local asset joins where available.
7. Source assets are not rewritten merely for DOCX compatibility.
8. Ambiguous historical local links are never resolved by guessing.
9. Missing visible attachments are represented explicitly.
10. Canonical-data/deletion/visibility/link-semantics changes require explicit documentation and migration consideration.

`FROZEN_VERSION.md` records the historical v2.7 preservation baseline. The
exporter-core refactor preserves those authority rules.

## Performance and diagnostics

The normal archive path is incremental. The CORE index checks the stored source
path and mtime before provider normalization, so unchanged conversation files are
skipped immediately.

Expensive whole-archive diagnostics are intentionally **opt-in** rather than run
on every daily update. This includes the cumulative asset-reference audit and the
full CORE/legacy compatibility oracle.

Run the formal current-batch compatibility validator explicitly with:

```text
py -m gpt_exporter.validation_cli
```

Run it over the complete archive only when deliberately required:

```text
py -m gpt_exporter.validation_cli --all
```

## Advanced / compatibility CLI

The GUI is the recommended entry point, but historical command-line entry points
remain intentionally supported for diagnostics and advanced use.

Run the cumulative ChatGPT archive workflow:

```text
py archive_chats.py
```

Rebuild derived exports from the existing archive:

```text
py archive_chats.py --convert-only
```

Build/update the historical CLI index surface:

```text
py index_chatgpt_archive.py index
```

Generate persistent Markdown explicitly:

```text
py export_all.py --markdown-only --overwrite-all
```

Deliberate destructive reset/recovery:

```text
py archive_chats.py --fresh
```

`--fresh` is not intended for routine use.

## Main implementation areas

| Path | Purpose |
|---|---|
| `gpt_exporter_gui.py` | Main workspace-driven graphical application |
| `gpt_exporter/workspaces.py` | Workspace model, registry and persistence |
| `gpt_exporter/workflow.py` | Provider/workspace non-GUI workflow context |
| `gpt_exporter/providers/` | Source-provider contracts and implementations |
| `gpt_exporter/model.py` | Provider-neutral normalized conversation model |
| `gpt_exporter/export/` | CORE Markdown/DOCX/batch export implementations and compatibility oracles |
| `gpt_exporter/index/` | CORE SQLite/FTS writer plus compatibility implementation |
| `gpt_exporter/provider_pipeline.py` | Provider-aware archive orchestration bridge |
| `gpt_exporter/ui/` | Common workspace/provider/archive UI |
| `gpt_exporter/validation.py` | CORE/shadow/legacy compatibility validator |
| `collect_chatgpt_archive.js` | ChatGPT browser-side collector source |
| `archive_chats.py` and other root scripts | Historical compatibility/diagnostic CLI entry points |

The obsolete root `archive_gui_workflow.py` implementation was removed after its
responsibilities moved to the package UI and `WorkspaceWorkflow`.

## Development

Run the test suite:

```text
py -m unittest discover -s tests -v
```

Compile-check Python sources:

```text
py -m compileall -q .
```

GitHub Actions validates Python 3.12 and 3.13 on Windows and builds the Windows
`onedir` distribution.

## Formal ChatGPT CORE milestone

The final real-archive compatibility run on 2026-08-31 reported:

```text
Sources     : 2
Checked     : 2
Matched     : 2
Mismatched  : 0
Failed      : 0
```

The formal milestone record, retained compatibility seams and tag gate are in
`docs/EXPORTER_CORE_CHATGPT_VALIDATION.md`.

The milestone does **not** claim Discord integration. A second provider must
reuse this same CORE rather than recreate the application.

## Documentation

- `docs/EXPORTER_CORE_ARCHITECTURE.md` — detailed provider/workspace architecture.
- `docs/EXPORTER_CORE_CHATGPT_VALIDATION.md` — formal ChatGPT CORE validation/freeze record.
- `docs/ARCHITECTURE.md` — concise current architecture/data-authority overview.
- `docs/RELEASE_NOTES_V2.9.md` — historical public v2.9.0 packaging notes.
- `CHANGELOG.md` — release lineage and architecture milestones.
- `FROZEN_VERSION.md` — historical v2.7 preservation baseline.

## License

GPT Exporter is free software licensed under **GNU GPL v3 or later
(`GPL-3.0-or-later`)**. See `LICENSE`.
