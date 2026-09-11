# GPT Exporter

GPT Exporter is a Windows-oriented local conversation archiver, exporter, indexer and Browser that is evolving from a ChatGPT-specific tool into a provider-neutral multi-source application.

The current development line includes **ChatGPT** and **Discord** providers. The shared application provides the canonical model, SQLite search/indexing, Browser/workspace shell, common archive workflow/progress UI, persistent logs, and shared Markdown/DOCX rendering. Service-specific collection and source interpretation live below `gpt_exporter/providers/`.

> [!IMPORTANT]
> GPT Exporter processes private conversation data and temporary browser-session material. Never publish generated archives, browser exports, SQLite indexes, cookies, tokens, account identifiers, or private attachments. See `SECURITY.md`.

## Current architecture

The application is already substantially provider-neutral:

```text
shared GUI / CLI / application
          |
          v
canonical core + workspaces + index + export + Browser
          |
          v
provider contracts/actions
          |
          +--> ChatGPT
          +--> Discord
```

However, the provider packages are **not yet fully dynamically installable**: `gpt_exporter/application.py` still explicitly composes the known ChatGPT and Discord implementations. The next architectural milestone will replace this with provider discovery/capabilities so adding or removing a provider requires no edit to the main application.

See:

- `docs/ARCHITECTURE.md` — current architecture and boundaries;
- `docs/PROVIDER_PACKAGE_ARCHITECTURE.md` — next provider-package milestone specification;
- `docs/HANDOVER_PROVIDER_PACKAGING.md` — development handover for that milestone;
- `docs/TODO.md` — deliberately deferred work.

After provider independence/packageability is proven, the planned future project identity is **Multi Social Network Explorer (MSNE)**. The rename is intentionally a later milestone.

## Shared application principles

The main design rules are:

1. Provider-specific source schemas never become assumptions of the shared canonical model.
2. The Browser, workspace shell, indexing, organization, progress/log UI and generic rendering stay shared.
3. Providers supply source-specific capabilities/data rather than separate application experiences.
4. Important behavior must work independently of Tkinter; GUI and CLI are clients of the same library/provider operations.
5. Durable archive data is preserved conservatively; derived DOCX/SQLite outputs remain rebuildable.
6. Provider-specific destructive remote actions must not silently damage the local canonical archive.

## Requirements

- Windows 10 or later is the primary tested platform.
- Python 3.12 or newer for source execution/development.
- A modern browser with Developer Tools for the current browser-collector workflows.
- Dependencies from `requirements.txt` / `pyproject.toml`.

Install dependencies:

```text
py -m pip install -r requirements.txt
```

Optional environment check:

```text
py check_environment.py
```

A self-contained Windows `onedir` build is also supported by the release/build automation.

## Starting the application

From source:

```text
py gpt_exporter_gui.py
```

The shared application opens the active named conversation workspace. Current default provider workspaces are based on the installed ChatGPT and Discord implementations.

Historical explicit provider launch paths remain available during migration:

```text
py gpt_exporter_gui.py --provider gpt
py gpt_exporter_gui.py --provider discord
```

These are compatibility paths, not the final provider-package interface.

## Shared archive workflow

ChatGPT and Discord use the same provider-neutral archive workflow window and processing lifecycle.

The shared UI owns:

- service/collector/download workflow presentation;
- automatic detection lifecycle;
- background archive processing;
- progress display;
- persistent logs;
- success/failure behavior;
- Browser refresh completion handling.

Provider actions supply the service-specific collector, validation, source/archive operation and text required by that workflow.

Persistent workflow logs are written below the active workspace's `reports` directory using timestamped files plus `archive-workflow-latest.log`.

## ChatGPT provider

ChatGPT remains the historical provider and preserves the cumulative/non-destructive archive rules established by the frozen v2.7 line.

Its provider directory owns ChatGPT-specific browser collection, source-schema interpretation, historical compatibility and archive behavior. Once data reaches the canonical boundary, shared indexing/Browser/rendering infrastructure is used wherever appropriate.

The historical default workspace remains under:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

See `FROZEN_VERSION.md`, `docs/RELEASE_NOTES_V2.8.md`, and `docs/RELEASE_NOTES_V2.9.md` for the historical release lineage.

## Discord provider

Discord is the second current provider. Its normal workflow uses a browser collector against the selected authenticated DM and archives the result into a cumulative canonical conversation.

The default workspace is:

```text
%USERPROFILE%\Documents\Discord Archive
```

Current Discord features include:

- locale-tolerant current-user detection;
- explicit history-completeness diagnostics for the virtualized Discord scroller;
- cumulative merge by stable message ID;
- conservative `(edited)` / `(deleted)` history semantics;
- raw collector snapshot plus cumulative canonical XZ archive;
- shared Browser/index integration;
- human symmetric DM titles/filenames;
- compact participant/avatar DOCX header using display names;
- shared chat-style DOCX rendering;
- safe remote deletion of already archived own messages after dry-run coverage verification;
- `Regenerate Missing DOCX…` maintenance workflow;
- density-based multipart DOCX for large DMs.

See `docs/DISCORD_PROVIDER.md` for details.

## Discord multipart DOCX

Large DMs remain **one canonical conversation** and **one Browser row**, but may produce several derived DOCX files.

The current split threshold is 1,000 messages. Sparse historical years may be grouped; dense periods split by semester and then quarter, with quarter as the minimum granularity.

The real 6,674-message Gadget MCS ↔ Littleloulita validation produced:

```text
2022-2025 : 37 messages
2026Q1    : 1,872 messages
2026Q2    : 2,550 messages
2026Q3    : 2,215 messages
```

Observed DOCX page counts and byte sizes differed strongly enough to confirm that page count is not a reliable split criterion. The Browser currently opens the latest part; richer multipart navigation and changed-period-only regeneration are deferred in `docs/TODO.md`.

## Search and organization

The shared Browser provides SQLite FTS5 search and provider-neutral organization facilities including projects, categories and tags. Incremental indexing preserves Browser-managed organizational metadata.

The canonical index stores provider metadata generically so a new service should not require adding service-specific columns to the shared conversation table.

## Archive preservation principles

The project follows conservative preservation rules:

- normal archive updates are cumulative/non-destructive unless an explicitly documented provider operation says otherwise;
- missing data in a partial recapture must not silently erase known history;
- ambiguous asset mappings are not guessed;
- source assets are not rewritten merely for DOCX compatibility;
- DOCX and SQLite are derived/rebuildable presentation/index artifacts;
- changes to canonical data, deletion policy, collection breadth, visible semantics, or asset-link semantics require explicit documentation and migration/rollback consideration.

For Discord specifically, remote deletion affects the remote service only; it does not delete the local canonical archive.

## CLI and library use

The GUI is a normal user entry point, but the architecture does not make Tkinter the business-logic layer.

Core/provider archive operations must remain usable as Python/library/command-line operations. Historical command wrappers are retained during migration, and the next provider-package milestone will formalize provider-neutral CLI capability dispatch alongside GUI discovery.

## Provider packaging — next milestone

The next major refactor must make provider independence literal:

```text
remove ChatGPT package -> app/CLI still work with Discord
remove Discord package -> app/CLI still work with ChatGPT
remove all providers -> shared application imports/startup remain valid
add unknown provider package -> discovered without editing main-app source
```

A future provider such as `export-provider-linkedin` should be developable in its own repository against a stable provider API/SDK, produce an installable artifact, and appear in the shared GUI/CLI without adding LinkedIn-specific branches to the main exporter.

The final package/distribution mechanism is deliberately undecided; architectural independence comes first. See `docs/PROVIDER_PACKAGE_ARCHITECTURE.md`.

## Development

Run the test suite with:

```text
py -m unittest discover -s tests -v
```

Compile-check the Python sources:

```text
py -m compileall -q .
```

GitHub Actions validates supported Windows/Python combinations and builds the Windows `onedir` application. Because the current provider work has been developed as stacked pull requests, always inspect the current CI state before declaring the whole branch green; obsolete tests may need reconciliation with intentionally changed semantics.

See `CONTRIBUTING.md` before changing archive semantics or provider boundaries.

## Documentation

The documentation index is `docs/README.md`.

Important current documents:

- `docs/ARCHITECTURE.md`
- `docs/DISCORD_PROVIDER.md`
- `docs/PROVIDER_SELECTION.md`
- `docs/PROVIDER_PACKAGE_ARCHITECTURE.md`
- `docs/HANDOVER_PROVIDER_PACKAGING.md`
- `docs/TODO.md`
- `CHANGELOG.md`
- `FROZEN_VERSION.md`

## License

GPT Exporter is free software licensed under **GNU GPL v3 or later (`GPL-3.0-or-later`)**. See `LICENSE`.
