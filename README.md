# Multi Social Network Explorer (MSNE)

**Multi Social Network Explorer (MSNE)** is a Windows-oriented local conversation archiver, exporter, indexer and Browser built around independently packaged providers.

The current development line includes **ChatGPT** and **Discord** providers. The shared host supplies the canonical model, SQLite search/indexing, Browser/workspace shell, common archive workflow/progress UI, persistent logs, and shared Markdown/DOCX infrastructure. Service-specific collection, source interpretation and provider actions live in the independently packaged distributions under `packages/export-provider-chatgpt` and `packages/export-provider-discord`.

> [!IMPORTANT]
> MSNE processes private conversation data and temporary browser-session material. Never publish generated archives, browser exports, SQLite indexes, cookies, tokens, account identifiers, or private attachments. See `SECURITY.md`.

## Current architecture

The host is provider-neutral and discovers providers through the stable `gpt_exporter.provider_plugins` entry-point contract:

```text
shared GUI / CLI / application
          |
          v
canonical core + workspaces + index + export + Browser
          |
          v
provider SDK / discovery / composition hooks
          |
          +--> export-provider-chatgpt
          +--> export-provider-discord
          +--> independently developed future providers
```

The host is valid with zero providers installed. ChatGPT-only, Discord-only, both-provider and zero-provider installation matrices are covered by tests, and an unknown synthetic provider can participate through the shared composition hooks without edits to the application core.

The historical Python distribution/import identities remain `gpt-exporter` and `gpt_exporter` during the controlled rename. This is intentional compatibility, not unfinished branding. See `docs/MSNE_RENAME_INVENTORY.md` and issue #86 for the migration plan.

See also:

- `docs/ARCHITECTURE.md` — shared architecture and boundaries;
- `docs/PROVIDER_PACKAGE_ARCHITECTURE.md` — provider-package design and compatibility contract;
- `docs/HANDOVER_PROVIDER_PACKAGING.md` — provider extraction history/handover;
- `docs/TODO.md` — deliberately deferred work.

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

For a source checkout that needs both current providers:

```text
py -m pip install --no-deps -e packages/export-provider-chatgpt -e packages/export-provider-discord
```

For the ChatGPT provider's environment diagnostics:

```text
py -m export_provider_chatgpt.cli.check_environment
```

A self-contained Windows `onedir` build is supported by the release/build automation.

## Starting the application

From source, use the canonical MSNE launcher:

```text
py msne.py
```

The shared application opens the active named conversation workspace and discovers installed providers dynamically.

Explicit provider selection remains available through the shared launcher:

```text
py msne.py --provider gpt
py msne.py --provider discord
```

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

ChatGPT is the historical provider and preserves the cumulative/non-destructive archive rules established by the frozen v2.7 line.

Its extracted distribution owns ChatGPT-specific browser collection, source-schema interpretation, historical compatibility and archive behavior. Once data reaches the canonical boundary, shared indexing/Browser/rendering infrastructure is used wherever appropriate.

The historical default workspace remains:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

This provider data path is deliberately not renamed as part of the MSNE product rename.

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

The Browser currently opens the latest part; richer multipart navigation and changed-period-only regeneration are deferred in `docs/TODO.md`.

## Search and organization

The shared Browser provides SQLite FTS5 search and provider-neutral organization facilities including projects, categories and tags. Incremental indexing preserves Browser-managed organizational metadata.

The canonical index stores provider metadata generically so a new service does not require adding service-specific columns to the shared conversation table.

## Archive preservation principles

MSNE follows conservative preservation rules:

- normal archive updates are cumulative/non-destructive unless an explicitly documented provider operation says otherwise;
- missing data in a partial recapture must not silently erase known history;
- ambiguous asset mappings are not guessed;
- source assets are not rewritten merely for DOCX compatibility;
- DOCX and SQLite are derived/rebuildable presentation/index artifacts;
- changes to canonical data, deletion policy, collection breadth, visible semantics, or asset-link semantics require explicit documentation and migration/rollback consideration.

For Discord specifically, remote deletion affects the remote service only; it does not delete the local canonical archive.

## Provider packaging

Providers are separate installable distributions. The host contract is intentionally stable during the MSNE rename:

```text
gpt_exporter.provider_sdk
gpt_exporter.provider_plugins
```

Removing ChatGPT does not invalidate Discord; removing Discord does not invalidate ChatGPT; removing both still leaves a valid provider-neutral host. The Windows onedir build installs the provider distributions separately and freezes their package code, resources and entry-point metadata.

A future provider can therefore be developed independently against the public SDK/entry-point contract rather than by adding service-specific branches to the host.

## Development

Run the test suite with:

```text
py -m unittest discover -s tests -v
```

Compile-check the Python sources:

```text
py -m compileall -q .
```

GitHub Actions validates supported Windows/Python combinations and builds the Windows `onedir` application.

See `CONTRIBUTING.md` before changing archive semantics or provider boundaries.

## Documentation

The documentation index is `docs/README.md`.

Important current documents:

- `docs/ARCHITECTURE.md`
- `docs/DISCORD_PROVIDER.md`
- `docs/PROVIDER_SELECTION.md`
- `docs/PROVIDER_PACKAGE_ARCHITECTURE.md`
- `docs/HANDOVER_PROVIDER_PACKAGING.md`
- `docs/MSNE_RENAME_INVENTORY.md`
- `docs/TODO.md`
- `CHANGELOG.md`
- `FROZEN_VERSION.md`

## License

Multi Social Network Explorer (MSNE) is free software licensed under **GNU GPL v3 or later (`GPL-3.0-or-later`)**. See `LICENSE`.
