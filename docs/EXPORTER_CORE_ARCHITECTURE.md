# Exporter CORE Architecture

This document defines the provider-driven architecture used by GPT Exporter.
The ChatGPT implementation is the validated reference provider. The architecture
may evolve for additional providers, but common functionality must remain in
CORE rather than being reimplemented per provider.

## Compatibility rule

The exporter-core work is an architectural refactor, not a behavioral rewrite.
For ChatGPT the historical exporter remained the oracle until equivalence was
demonstrated.

Given the same preserved native source, the CORE path must preserve:

- cumulative/non-destructive conversation and asset retention;
- `current-batch` selection;
- visible/exported message selection and order;
- indexed message selection/order/roles/IDs/searchable text;
- Markdown and DOCX semantics, including asset references;
- search results and FTS content;
- Projects, Tags and Categories;
- native provider provenance/origin metadata;
- archive layout and canonical-source preservation.

Unexplained differences are regressions.

## Core responsibilities

Exporter CORE owns:

- the Tk application shell and archive browser;
- workspace selection and workspace management;
- provider registry/management UI;
- project, category and tag management;
- SQLite/FTS search and message previews;
- keyword cloud;
- standard archive filesystem layout;
- task/progress/logging infrastructure;
- common asset storage/audit infrastructure;
- provider-neutral normalized conversation data;
- Markdown rendering from normalized conversations;
- DOCX conversion from Markdown;
- normalized SQLite/FTS writing;
- opening/revealing generated files;
- configuration, packaging and application lifecycle.

The common archive layout is:

```text
<archive root>/
    downloads/
    assets/
    reports/
    markdown/
    conversations-index.sqlite
    *.docx
```

A provider supplies a default archive directory name. A workspace owns the
actual archive root used by one archive instance.

## Workspace model

`Workspace` and `Provider` are separate concepts.

```text
Workspace
    key
    display_name
    provider
    archive_root
```

A provider describes source-specific capabilities. A workspace selects one
provider plus one archive root/database. This supports multiple physically
separate archives using the same provider.

`WorkspaceWorkflow` is the main GUI's single runtime workflow context. It binds
provider, archive root, database, acquisition, archive execution and CORE index
update together. Switching workspace changes those as one atomic operating
context.

The GUI no longer maintains a parallel ChatGPT-specific workflow object.

## Provider responsibilities

A provider owns only source-specific behavior:

- provider identity and website URL;
- source-bundle naming and validation;
- collector/acquisition mechanism;
- native-format parsing/import preservation;
- attachment/reply/reaction/reference semantics that are native to the source;
- normalization into the common model;
- source-specific provenance/origin detection;
- optional actions that genuinely cannot be expressed by CORE.

A provider must not implement its own archive browser, project tree, search
engine, keyword cloud, generic DOCX renderer, generic logging UI, provider
manager, workspace selector or archive layout.

## Normalized data flow

```text
provider-native source
        |
        v
provider importer / canonical preservation
        |
        v
provider normalizer
        |
        v
common Conversation model
        |
        +--> display projection --> CORE Markdown --> common DOCX converter
        |
        +--> search projection --> CORE SQLite / FTS
        |
        +--> normalized origins/index metadata --> CORE provenance writer
        |
        +--> Browser / Search / Projects / Tags / Categories / Keywords
```

The common GUI/search/export layers do not read provider-native JSON directly.

A provider may expose distinct display and search projections. ChatGPT requires
this for compatibility: the display projection follows the historical active
conversation branch, while the search projection reproduces the historical
mapping-wide indexing rules.

Provider-native source remains preserved separately. The normalized model and
all outputs derived from it are rebuildable and must never replace canonical
provider data.

## ChatGPT reference provider

`CHATGPT_PROVIDER` supplies:

- ChatGPT identity and website;
- packaged browser collector;
- `chatgpt-archive-source.json` bundle contract;
- cumulative native importer;
- ChatGPT normalizer;
- historical asset-index plus local-fallback resolution semantics;
- ChatGPT provenance/origin extraction.

The normal production pipeline still exposes the historical five stages:

```text
1/5 - Import ChatGPT archive bundle
2/5 - Inventory media references
3/5 - Build asset manifest
4/5 - Export new or larger conversations
5/5 - Update archive search index
```

Stages 4 and 5 are now authoritative CORE stages:

- Markdown is rendered from the normalized display projection;
- DOCX uses the common converter;
- SQLite/FTS is written from the normalized search projection.

`Archive -> Update Search Index` uses the current `WorkspaceWorkflow` and the
same CORE indexer.

## Incremental behavior and performance

The normalized index checks stored source path plus mtime before provider
normalization. An unchanged file at the same path is skipped immediately.
Modified, renamed, moved or forced files pass through full normalization.

Two expensive diagnostics are deliberately not part of every daily archive run:

- cumulative asset-reference audit;
- full CORE/shadow/legacy compatibility oracle.

Both remain explicit diagnostics. `python -m gpt_exporter.validation_cli` checks
`reports/current-batch.json`; `--all` performs a full-archive validation.

## Compatibility/oracle code intentionally retained

Cleanup must distinguish dead code from frozen compatibility code.

The following are intentionally retained:

- historical root CLI entry points (`archive_chats.py`, `export_all.py`,
  `export_markdown.py`, `export_docx.py`, `index_chatgpt_archive.py`, etc.);
- packaged `_legacy_*` modules that encode the historical behavior used by
  compatibility wrappers and/or validation oracles;
- `ProviderWorkflow`, the provider-level non-GUI workflow composed by
  `WorkspaceWorkflow`;
- the ChatGPT pipeline guard that rejects unsupported providers before archive
  mutation.

The obsolete root `archive_gui_workflow.py` and its dedicated tests were removed
after the package UI and `WorkspaceWorkflow` fully replaced that implementation.
The unused `CHATGPT_WORKFLOW` singleton was removed at the same cleanup milestone.

## Preservation rule

Canonical data authority remains:

```text
downloads/*.json.xz + assets/*   canonical durable source
DOCX / Markdown                  derived/rebuildable
SQLite / FTS                     derived search/organization index
reports / manifests / caches    diagnostics/optimizations
```

Normal archive updates remain cumulative and non-destructive. Conversations or
assets missing from a later bundle are not deleted. Source assets are not
rewritten merely for DOCX compatibility. Ambiguous historical links are not
guessed. Missing visible attachments remain explicit.

## Formal ChatGPT acceptance

The ChatGPT CORE gate was closed on 2026-08-31.

The final real-archive command was:

```text
py -m gpt_exporter.validation_cli
```

It compared production CORE, shadow CORE, historical index, historical Markdown
and historical DOCX for the current batch and produced:

```text
Sources     : 2
Checked     : 2
Matched     : 2
Mismatched  : 0
Failed      : 0
```

DOCX comparison is semantic: volatile package metadata is ignored and local
OOXML relationship targets are resolved before comparison. Tests separately
verify that relationships resolving to different assets remain mismatches.

See `EXPORTER_CORE_CHATGPT_VALIDATION.md` for the formal freeze/tag record.

## Architectural acceptance test

If the ChatGPT provider were removed, CORE should still know how to:

- represent an archive and workspace;
- launch/manage the common GUI;
- list/manage providers;
- browse/index normalized conversations;
- search and organize them;
- render keyword clouds and derived exports;
- manage common assets and logs.

It should not know how to collect or interpret ChatGPT-native data.

Conversely, the ChatGPT provider must contain no duplicate GUI, search engine,
project-management implementation, keyword-cloud implementation, workspace
selector or generic DOCX renderer.

## Next architecture test

No Discord code is part of this ChatGPT milestone. Discord is the next provider
only after this milestone is frozen/tagged. Its integration succeeds only if it
reuses the same CORE/workspace UI/GUI and limits its implementation to genuinely
source-specific behavior.
