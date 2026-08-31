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

A provider may select the default archive root name, but it must not redefine
the layout below that root.

## Provider responsibilities

A provider owns only source-specific behavior:

- provider identity and website URL;
- collector or acquisition mechanism;
- downloaded source-bundle naming and validation;
- native-format parsing;
- source-specific attachment/reference decoding;
- normalization into the common conversation model;
- optional source-specific actions that cannot be expressed by the core.

Providers must not implement their own archive browser, project tree, search
engine, keyword cloud, generic DOCX renderer, generic logging UI, provider
manager, or archive filesystem layout.

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
        +--> Browser / search / projects / tags / keyword cloud
```

A provider may expose different display and search projections from the same
native conversation. For ChatGPT this distinction is required for compatibility:
DOCX/Markdown follows the active branch, while the historical SQLite index uses
its established mapping-wide visibility/indexability rules. The common model
therefore carries provider-defined display/search flags and ordering rather than
forcing both outputs through one lossy message list.

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
10. Provider-aware GUI workflow and compatibility pipeline bridge: done.
11. Non-destructive shadow validation against the production index: done.
12. Reach zero unexplained shadow differences for ChatGPT message/title semantics.
13. Preserve/compare remaining ChatGPT native provenance and organization fields.
14. Switch primary ChatGPT index/export stages behind compatibility guards.
15. Move remaining ChatGPT-specific asset-reference rules behind the provider.
16. Verify GPT Exporter behavior against characterization and real-archive tests.
17. Integrate Discord as the second provider using the same core and GUI.

## Architectural acceptance test

If the ChatGPT provider is removed, the core should still know how to:

- represent an archive;
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
manager, or generic DOCX renderer.
