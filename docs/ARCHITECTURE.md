# Architecture

GPT Exporter is evolving toward a provider-neutral conversation archive engine. ChatGPT is one provider implementation, not an architectural dependency of the core.

## Dependency rule

The most important invariant is one-way dependency:

```text
providers\gpt  ------>  core
providers\discord  -->  core
providers\...  ----->  core

core  -X->  providers\*
```

The core must never import a concrete provider. Deleting `gpt_exporter\providers\gpt\` should not make the provider-neutral core unimportable or unusable by another provider.

Provider-specific source schemas are normalized into shared objects before generic indexing, search, export, asset handling, or UI logic consumes them.

## Canonical provider boundary

Concrete providers implement `gpt_exporter.core.ConversationProvider` and produce:

```text
CanonicalConversation
CanonicalMessage
CanonicalAsset
```

The canonical model contains only cross-provider concepts. Provider-only fields belong in the `metadata` mapping and must not become required core fields merely because one provider exposes them.

Examples of provider-only ChatGPT metadata include Custom GPT / Project identifiers, model slugs, gizmo identifiers and ChatGPT-specific origin fields. A future Discord provider can expose Discord-specific channel, guild, thread or attachment metadata without changing the core model.

## Target package structure

```text
gpt_exporter\
├── core\                   # provider-neutral contracts/model and, progressively, engine APIs
├── archive\                # shared archive/asset services being generalized
├── export\                 # shared Markdown/DOCX output services
├── index\                  # shared search/index services being generalized
├── ui\                     # shared UI components/workflows
└── providers\
    ├── gpt\                # ChatGPT-specific ingestion/normalization
    │   └── archive\
    │       └── legacy_docx\ # completed historical migration material, not core runtime
    └── discord\            # future provider
```

`gpt_exporter/legacy/` and the old ChatGPT-specific pipeline/index implementation are transitional locations. They are not part of the target core architecture and will be migrated only after their data paths no longer depend on historical DOCX inputs.

## Current ChatGPT archive flow

The existing ChatGPT provider currently uses:

```text
Authenticated ChatGPT tab
        |
        v
collect_chatgpt_archive.js
        |
        v
chatgpt-archive-source.json
        |
        v
import/browser processing
        |
        +--> downloads\*.json.xz
        +--> assets\*
```

`gpt_exporter.providers.gpt.ChatGPTProvider` is the first adapter that converts an archived ChatGPT conversation JSON/XZ file to the provider-neutral canonical model. Existing archive/index/export paths remain compatible while later refactors move them behind the canonical boundary.

## Shared engine responsibilities

Once provider data is canonical, shared code owns:

- durable archive layout and generic provenance;
- message/conversation indexing and search;
- Markdown and DOCX generation;
- provider-neutral asset handling;
- categories, tags and work-project organization;
- generic browser/UI behavior.

Provider code owns:

- source discovery and acquisition;
- source-schema parsing;
- provider-specific visibility rules;
- mapping provider metadata to canonical metadata;
- provider-specific diagnostics or historical migrations.

## Legacy ChatGPT DOCX migration

The 42 historical DOCX conversations have been reconstructed and validated. The legacy DOCX pipeline is therefore a completed ChatGPT-provider migration, not a generic engine feature.

Before removing the historical DOCX sources and active legacy runtime code, the normalized JSON must become sufficient for a complete archive rebuild without consulting those DOCX files. After that cutover, the DOCX parser/role-inference/reconstruction/audit implementation belongs under `providers\gpt\archive\legacy_docx\` as archived migration material (or can later be removed entirely if repository-retention policy allows it).

## Data authority

For provider-native archived conversations, normalized durable source data and preserved assets are authoritative. DOCX/Markdown and SQLite remain derived.

A provider may have a one-time migration source (such as historical ChatGPT DOCX). Once migration output is promoted to the canonical provider archive and independently rebuildable, the migration source is no longer a runtime dependency.

## Architecture acceptance criterion

A provider-neutral release should be able to satisfy this thought experiment:

```text
Remove gpt_exporter\providers\gpt\.
Install/use another provider.
The core model, index/search engine, exporters and generic UI still work.
```

Automated architecture tests enforce the first part of this rule by rejecting imports from `gpt_exporter.core` into the concrete provider namespace.

## Versioning rule

v2.7 remains the frozen behavioral baseline for existing ChatGPT archive behavior while provider extraction proceeds. Refactors must preserve current user-visible behavior unless accompanied by explicit migration/changelog/rollback treatment.
