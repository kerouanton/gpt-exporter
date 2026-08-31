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

## Core responsibilities

The exporter core owns:

- the Tk application shell and archive browser;
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
engine, keyword cloud, generic DOCX renderer, generic logging UI, or archive
filesystem layout.

## Preservation rule

Provider-native source data remains preserved according to that provider's
compatibility and retention rules. Normalized data and derived outputs must not
silently replace or destructively rewrite provider-native canonical data.

For ChatGPT, the existing cumulative/non-destructive preservation invariants
remain authoritative until explicitly migrated with compatibility tests.

## Initial provider boundary

`gpt_exporter.providers.ExporterProvider` is the first explicit provider
contract. The initial `CHATGPT_PROVIDER` keeps the existing ChatGPT importer and
collector unchanged behind that boundary.

The contract will grow only when a second real provider requires a capability.
Discord is intentionally kept paused until ChatGPT operates through the common
core, so the abstraction is driven by two real implementations rather than by
speculation.

## Migration strategy

The refactor is incremental. Repository-root compatibility wrappers and frozen
ChatGPT behavior remain available while responsibilities move behind library
APIs.

Recommended order:

1. Introduce provider identity and source-acquisition metadata.
2. Make archive paths and application identity provider-neutral.
3. Make GUI/browser naming provider-neutral while preserving behavior.
4. Separate generic workflow/task/logging infrastructure from ChatGPT-specific
   acquisition instructions.
5. Route source import through the provider boundary.
6. Introduce the normalized conversation model.
7. Split ChatGPT-native parsing from common Markdown/index generation.
8. Move ChatGPT-specific asset-reference rules behind the provider.
9. Verify GPT Exporter behavior against characterization tests.
10. Integrate Discord as the second provider using the same core and GUI.

## Architectural acceptance test

If the ChatGPT provider is removed, the core should still know how to:

- represent an archive;
- launch its GUI;
- browse/index normalized conversations;
- search and organize them;
- render keyword clouds and derived exports;
- manage common assets and logs.

It should no longer know how to collect, parse, or interpret ChatGPT-native
data.

Conversely, the ChatGPT provider must contain no duplicate GUI, search engine,
project-management implementation, keyword-cloud implementation, or generic
DOCX renderer.
