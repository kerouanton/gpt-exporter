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
are rendered from `current_workspace.provider` rather than hard-coded strings.

`WorkspaceWorkflow` is the non-GUI operating-context object. It binds one
workspace to its provider workflow and archive root so acquisition/archive
operations cannot accidentally mix one provider with another workspace's paths.
Compatibility singletons remain only while legacy callers are migrated.

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
The shadow validator compares these provenance outputs against the production
SQLite database before the normalized writer can become authoritative.

Provider-native source data remains preserved separately. The normalized model
is rebuildable and must never silently replace or destructively rewrite native
canonical data.

## Provider registry

`ProviderRegistry` is owned by exporter core. Built-in providers are registered
once and surfaced through the common GUI. The first management surface is
`Providers -> Manage Providers...`, which lists provider identity, default
archive, collector, and website.

The registry is intentionally compatible with future external/installable
providers; those providers must not need to implement their own application UI.

## Preservation rule

Provider-native source data remains preserved according to that provider's
compatibility and retention rules. Normalized data and derived outputs must not
silently replace or destructively rewrite provider-native canonical data.

For ChatGPT, the existing cumulative/non-destructive preservation invariants
remain authoritative until explicitly migrated with compatibility tests.

## Current provider boundary

`gpt_exporter.providers.ExporterProvider` is the explicit provider contract. The
`CHATGPT_PROVIDER` keeps the existing ChatGPT collector/importer behavior behind
that boundary and declares its normalizer into the common model.

Discord remains paused until ChatGPT operates through the common core, so the
abstraction is driven by real implementations rather than speculation.

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
13. `WorkspaceWorkflow` context binding provider operations to one archive root: done at CORE API level; GUI migration in progress.
14. Provider-aware GUI workflow and compatibility pipeline bridge: done.
15. Non-destructive shadow validation against the production index: done.
16. Reach zero unexplained shadow differences for ChatGPT message/title semantics: done on real appended conversations; continue characterization coverage.
17. Normalize/write/compare ChatGPT native provenance and origin fields: implemented; real-archive validation pending.
18. Switch primary ChatGPT index/export stages behind compatibility guards.
19. Move remaining ChatGPT-specific asset-reference rules behind the provider.
20. Verify GPT Exporter behavior against characterization and real-archive tests.
21. Integrate Discord as the second provider using the same core, workspace UI, and GUI.

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
