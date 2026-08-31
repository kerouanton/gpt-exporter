# Exporter Core Architecture

This document defines the target architecture for turning GPT Exporter into a
provider-driven exporter framework while preserving the current ChatGPT archive
behavior as the reference implementation.

## Goal

One application core must provide the same user experience and archive layout
for ChatGPT, Discord, and future providers such as LinkedIn or Facebook.

The provider boundary exists only for source-specific collection and parsing.
The GUI, archive browsing, search, organization, keyword cloud, filesystem
layout, logging, derived exports, and common archive maintenance belong to the
core.

## Compatibility rule: architecture may change, results may not

The `architecture/exporter-core` branch is a refactor, not a behavioral rewrite.
For the ChatGPT provider, the pre-refactor GPT Exporter remains the behavioral
oracle until equivalence is demonstrated.

Given the same preserved native source, the refactored path must reproduce the
same observable results, including:

- preserved conversations and cumulative/non-destructive update semantics;
- `current-batch` selection;
- visible/exported message selection and order;
- indexed message selection, order, roles, IDs, and searchable text;
- Markdown/DOCX-derived content and asset references;
- search results and FTS content;
- Projects, Tags, Categories, and native-origin metadata;
- archive filesystem layout and canonical-source preservation.

Any unexplained difference is treated as a regression. A new common behavior is
introduced only after compatibility is established and the behavior change is
explicitly chosen rather than emerging accidentally from the refactor.

## Core responsibilities

The exporter core owns:

- the Tk application shell and archive browser;
- workspace selection and workspace-to-provider/archive binding;
- the provider registry and `Manage Providers` UI;
- project, category, and tag management;
- SQLite/FTS search and message previews;
- the keyword cloud;
- the standard archive filesystem layout;
- task execution, progress reporting, and persistent logs;
- common asset storage/audit infrastructure;
- provider-neutral normalized conversation data;
- Markdown rendering from normalized conversations;
- DOCX rendering from Markdown;
- opening/revealing generated files;
- configuration, packaging, and application lifecycle.

The standard archive layout remains identical for every provider:

```text
<archive root>/
    downloads/
    assets/
    reports/
    markdown/
    conversations-index.sqlite
    *.docx
```

A provider supplies its default archive directory name, but a workspace owns the
actual archive root selected by the user. The layout below that root remains a
core contract.

## Workspace model

A workspace is the application's current operating context. It references one
provider and one archive root:

```text
Workspace
    display_name
    provider
    archive_root
```

Typical default workspaces are:

```text
ChatGPT
    provider     = chatgpt
    archive_root = %USERPROFILE%\Documents\ChatGPT Archive

Discord
    provider     = discord
    archive_root = %USERPROFILE%\Documents\Discord Archive
```

`Workspace` and `Provider` are deliberately different concepts. A provider
contains source-specific capabilities; a workspace selects where one instance of
those capabilities operates. This permits multiple workspaces to use the same
provider later, for example a personal ChatGPT archive and a work ChatGPT
archive.

The GUI is driven by `current_workspace`. Selecting a workspace changes the
active provider, archive root, SQLite database, search/project/tag/category
context, collector, source-bundle name, website action, reports, and derived
outputs together. Provider-specific labels such as `Archive -> Open ChatGPT`
are rendered from the current workspace provider rather than hard-coded strings.

`WorkspaceWorkflow` is the non-GUI operating-context object and the main GUI's
single runtime workflow context. It owns the selected workspace's provider,
archive root, database, acquisition actions, archive execution, and CORE index
update. This prevents an action from accidentally mixing one provider with
another workspace's paths. `ProviderWorkflow` and compatibility singletons remain
only as lower-level or legacy seams for callers that still require them.

Provider archives are physically separate. Shared behavior lives in the code and
UI, not in a combined data directory.

## Provider responsibilities

A provider owns only source-specific behavior:

- provider identity and website URL;
- collector or acquisition mechanism;
- downloaded source-bundle naming and validation;
- native-format parsing;
- source-specific attachment/reference decoding;
- normalization into the common conversation model;
- source-specific origin/provenance detection;
- optional source-specific actions that cannot be expressed by the core.

Providers must not implement their own archive browser, project tree, search
engine, keyword cloud, generic DOCX renderer, generic logging UI, provider
manager, workspace selector, or archive filesystem layout.

## Normalized data flow

```text
provider-native source
        |
        v
provider importer / preservation
        |
        v
provider normalizer
        |
        v
common Conversation model
        |
        +--> display projection --> common Markdown renderer --> DOCX renderer
        |
        +--> search projection --> common SQLite / FTS index writer
        |
        +--> normalized origins / index metadata --> common SQLite provenance writer
        |
        +--> Browser / search / projects / tags / keyword cloud
```

A provider may expose different display and search projections from the same
native conversation. For ChatGPT this distinction is required for compatibility:
DOCX/Markdown follows the active branch, while the historical SQLite index uses
its established mapping-wide visibility/indexability rules. The common model
therefore carries provider-defined display/search flags and ordering rather than
forcing both outputs through one lossy message list.

Native provenance is normalized too. CORE receives provider-neutral
`ConversationOrigin` records plus compatibility index metadata; it does not walk
ChatGPT-native JSON to discover projects, Custom GPTs, templates, or model data.
The normalized SQLite writer is now authoritative for the production ChatGPT
index. Explicit shadow/legacy validation remains available as a diagnostic oracle
rather than running on every daily archive update.

Provider-native source data remains preserved separately. The normalized model
is rebuildable and must never silently replace or destructively rewrite native
canonical data.

## Production and validation paths

The normal ChatGPT archive path now uses CORE for both derived-output stages:

```text
current-batch native JSON
        |
        +--> provider normalization --> CORE Markdown --> common DOCX converter
        |
        +--> provider normalization --> CORE SQLite/FTS index
```

The expensive cumulative asset-reference audit and the full CORE/legacy shadow
oracle are deliberately opt-in diagnostics. They are not part of the normal
daily archive path because both scan or rebuild substantially more data than an
incremental update requires.

The normalized index also performs its unchanged-source check before provider
normalization. A source at the same path with the same stored mtime is skipped
immediately. Modified, renamed, moved, or forced sources still pass through full
normalization.

Explicit compatibility validation can compare:

- production CORE SQLite versus a shadow CORE SQLite database;
- production CORE SQLite versus the historical ChatGPT indexer;
- CORE Markdown versus historical Markdown exactly;
- production DOCX versus an historical DOCX oracle semantically.

DOCX package comparison ignores volatile core properties and resolves local
OOXML hyperlink relationship targets before comparing them. This prevents a
false mismatch when production and oracle DOCX files live in different
directories but their links resolve to the same archived asset.

## Provider registry

`ProviderRegistry` is owned by exporter core. Built-in providers are registered
once and surfaced through the common GUI. The management surface is
`Providers -> Manage Providers...`, which lists provider identity, default
archive, collector, and website.

The registry is intentionally compatible with future external/installable
providers; those providers must not need to implement their own application UI.

## Preservation rule

Provider-native source data remains preserved according to that provider's
compatibility and retention rules. Normalized data and derived outputs must not
silently replace or destructively rewrite provider-native canonical data.

For ChatGPT, the existing cumulative/non-destructive preservation invariants
remain authoritative. Production CORE stages preserve the same `current-batch`,
archive layout, and incremental source retention behavior.

## Current provider boundary

`gpt_exporter.providers.ExporterProvider` is the explicit provider contract. The
`CHATGPT_PROVIDER` keeps the existing ChatGPT collector/importer behavior behind
that boundary and declares its normalizer into the common model.

The ChatGPT production path now exercises the common Markdown/DOCX and
SQLite/FTS stages. Discord remains intentionally paused until the final explicit
ChatGPT equivalence check is complete, so the second provider tests the proven
boundary rather than defining it speculatively.

## Migration progress

1. Provider identity and source-acquisition metadata: done.
2. Provider-neutral archive paths: done.
3. Common acquisition helpers: done.
4. Provider-driven ingestion API: done.
5. Provider-neutral conversation model: done.
6. ChatGPT display/search projections preserving distinct legacy semantics: done.
7. Common Markdown/DOCX export path from normalized conversations: done.
8. Common normalized SQLite/FTS writer preserving project assignments: done.
9. Provider registry and `Manage Providers` UI: done.
10. Workspace abstraction and visible current-workspace selector: done.
11. Workspace-derived provider labels, collector, bundle name, archive root, and archive runner: done.
12. Persistent `Manage Workspaces` configuration and startup reload: done.
13. `WorkspaceWorkflow` as the main GUI runtime context, including archive execution and CORE `Update Search Index`: done.
14. Provider-aware GUI workflow and compatibility pipeline bridge: done.
15. Non-destructive CORE/legacy validation framework: done and now explicit/opt-in.
16. Zero unexplained ChatGPT message/title/index differences on real appended conversations: done.
17. ChatGPT provenance/origin normalization and real-archive equivalence validation: done.
18. Primary ChatGPT production SQLite/FTS index switched to CORE: done and real-archive validated.
19. Primary ChatGPT production Markdown/DOCX export switched to CORE: done; exact Markdown equivalence established.
20. ChatGPT asset-index/local-fallback merge semantics moved behind the provider projection: done.
21. Incremental index fast path and removal of expensive diagnostics from the daily archive path: done.
22. DOCX semantic oracle comparison for equivalent local relationship targets: done in automated tests.
23. Final explicit real-archive CORE/legacy equivalence run after the DOCX comparator fix: pending.
24. Refresh migration documentation and PR status: done on this branch.
25. Integrate Discord as the second provider using the same core, workspace UI, and GUI: next after final ChatGPT equivalence.

## Architectural acceptance test

If the ChatGPT provider is removed, the core should still know how to:

- represent an archive;
- represent/select a workspace;
- launch its GUI;
- list/manage installed providers;
- browse/index normalized conversations;
- search and organize them;
- render keyword clouds and derived exports;
- manage common assets and logs.

It should no longer know how to collect, parse, or interpret ChatGPT-native
data.

Conversely, the ChatGPT provider must contain no duplicate GUI, search engine,
project-management implementation, keyword-cloud implementation, provider
manager, workspace selector, or generic DOCX renderer.
