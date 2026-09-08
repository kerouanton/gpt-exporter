# Architecture

GPT Exporter is evolving into a provider-neutral conversation archive engine. ChatGPT is one provider implementation, not an architectural dependency of the engine.

## Dependency rule

The primary invariant is one-way dependency:

```text
providers\gpt      ------>  core/shared engine
providers\discord  ------>  core/shared engine
providers\...      ------>  core/shared engine

core/shared engine  -X->  providers\*
```

Concrete providers may depend on shared contracts and services. Shared engine code must not require a concrete provider to exist.

The strongest acceptance test is literal: deleting `gpt_exporter\providers\gpt\` must still leave the canonical model, serialization, canonical SQLite indexing, generic Markdown export, and generic resources operational. This is covered by `tests/test_provider_removal_resilience.py`, which copies the package, physically deletes the GPT provider directory, and exercises those services with a synthetic provider.

## Canonical provider boundary

Providers implement `gpt_exporter.core.ConversationProvider` and normalize their source schema into:

```text
CanonicalConversation
CanonicalMessage
CanonicalAsset
```

The canonical model contains only cross-provider concepts. Provider-only fields belong in provider metadata and must not become required core fields merely because one provider exposes them.

Examples of ChatGPT-only source concepts include `mapping`, `current_node`, gizmo/Custom GPT identifiers, ChatGPT project/origin details, model slugs, browser asset pointers, and `chatgpt-archive-source.json`. A future Discord provider can expose guild/channel/thread metadata without changing the canonical model or shared SQLite schema.

## Current package ownership

```text
gpt_exporter\
├── core\
│   ├── model.py                 # canonical provider-neutral model
│   ├── provider.py              # provider protocol
│   └── serialization.py         # canonical durable JSON/XZ
│
├── index\
│   ├── engine.py                # provider-neutral canonical index orchestration
│   ├── canonical.py             # CanonicalConversation -> SQLite
│   └── storage.py               # shared provider-neutral SQLite schema v5
│
├── export\
│   ├── markdown.py              # canonical Markdown + lazy compatibility facade
│   └── docx.py                  # shared Markdown -> DOCX
│
├── paths.py                     # explicit-root provider-neutral path model
├── resources\                   # shared HELP/HISTORY only
├── ui\                          # shared UI helpers
│
└── providers\
    └── gpt\
        ├── provider.py          # ChatGPT -> canonical adapter
        ├── paths.py             # historical ChatGPT default archive location
        ├── pipeline.py          # ChatGPT archive workflow
        ├── importer\            # browser-bundle import
        ├── indexing\            # native ChatGPT JSON indexing compatibility
        ├── export\              # native Markdown + batch workflow
        ├── archive\             # GPT asset inventory/manifest/audit
        ├── resources\           # collect_chatgpt_archive.js
        ├── cli\                 # ChatGPT-specific command implementations
        └── ui\                  # ChatGPT workflow and application shell
```

Historical root scripts remain only as compatibility launchers where existing commands must continue to work. They must not contain provider schema parsing or ChatGPT workflow logic.

## ChatGPT archive flow

The GPT provider currently owns this source-specific flow:

```text
Authenticated ChatGPT tab
        |
        v
providers\gpt\resources\collect_chatgpt_archive.js
        |
        v
chatgpt-archive-source.json
        |
        v
providers\gpt\importer / pipeline
        |
        +--> downloads\*.json.xz
        +--> assets\*
        |
        v
ChatGPTProvider -> CanonicalConversation
```

Existing native ChatGPT JSON/XZ behavior remains supported during the transition, but raw ChatGPT schema interpretation belongs to the provider.

## Shared engine responsibilities

Once provider data is canonical, shared code owns:

- canonical conversation/message/asset representation;
- durable canonical serialization;
- generic indexing and full-text search storage;
- canonical Markdown rendering and shared DOCX generation;
- categories, tags and work-project organization;
- generic UI components and browser behavior;
- path derivation from an explicit archive root.

Provider code owns:

- source discovery and acquisition;
- source-schema parsing and branch/visibility rules;
- provider-specific asset identifiers and metadata;
- provider-native compatibility import/index/export paths;
- provider-specific GUI actions and command-line workflows;
- provider-specific historical migrations;
- provider-specific default filesystem locations.

Shared code must not encode a concrete provider's archive directory name. New provider-neutral code constructs `ArchivePaths` with `ArchivePaths.from_root(explicit_root)`. Historical convenience defaults remain provider-owned and may be exposed through lazy compatibility shims only.

## Provider-neutral SQLite schema v5

Schema v5 removes the final ChatGPT-specific fields from the shared `conversations` table. Provider metadata is stored generically in:

```text
conversation_provider_metadata
    conversation_id
    provider_id
    metadata_json
    updated_at
```

The v4 fields:

```text
gizmo_id
gizmo_type
conversation_template_id
conversation_origin
default_model_slug
```

are migrated into `conversation_provider_metadata` with `provider_id = 'gpt'` and are no longer columns of the shared schema.

The migration is covered by tests that verify:

- all five legacy values are preserved;
- the five GPT columns disappear from `conversations`;
- child-table foreign keys remain valid after the table replacement;
- `PRAGMA foreign_key_check` returns no errors;
- another provider such as Discord can store its own metadata without any schema change.

## Legacy ChatGPT DOCX migration

The historical 42-conversation DOCX migration is closed. Its canonical promotion was verified from JSON only with:

- 42 / 42 conversations;
- 654 / 654 messages;
- exact role counts;
- zero DOCX dependencies in a rebuilt index.

The active `gpt_exporter\legacy` runtime package no longer exists. Historical reconstruction code is retained only as non-importable snapshot material under:

```text
gpt_exporter\providers\gpt\archive\legacy_docx\snapshot\
```

The original local DOCX migration directory is no longer a runtime or rebuild dependency.

## Compatibility facades

Some historical public imports remain outside `providers\gpt` so existing scripts and callers do not break abruptly. These facades obey two rules:

1. they contain no ChatGPT parsing/business logic;
2. generic package imports must not eagerly load `gpt_exporter.providers.gpt`.

New code should call provider APIs directly when performing provider-specific work.

## Architecture acceptance criteria

A provider-neutral engine must satisfy all of the following:

```text
1. Remove gpt_exporter\providers\gpt\ physically.
2. Import the canonical model and serialization code.
3. Serialize a conversation from a synthetic/non-GPT provider.
4. Build/update its SQLite index.
5. Export it to canonical Markdown.
6. Use shared resources/UI helpers.
7. No shared engine module imports a concrete provider as a runtime prerequisite.
8. No provider-specific fields are required by the shared SQLite schema.
9. Shared path derivation requires only an explicit archive root; concrete default paths belong to providers.
```

Provider compatibility facades may fail when their provider has deliberately been removed; the engine itself must not.

## Versioning rule

v2.7 remains the frozen behavioral baseline for established ChatGPT archive behavior while provider extraction proceeds. Refactors must preserve current user-visible behavior unless accompanied by explicit migration, changelog and rollback treatment.
