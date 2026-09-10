# Architecture

GPT Exporter is now a multi-provider conversation archive application in transition toward a fully packageable provider architecture. ChatGPT and Discord are concrete provider implementations; neither should become an architectural dependency of the shared engine.

The next architectural milestone is specified in `PROVIDER_PACKAGE_ARCHITECTURE.md`. That document deliberately distinguishes the **current provider-neutral foundation** from the stronger future requirement of independently installable/discoverable provider packages.

## Dependency rule

The primary invariant is one-way dependency:

```text
provider implementation  ------>  shared core/application contracts
shared core              -X---->  concrete provider implementation
```

Today the repository contains:

```text
gpt_exporter/providers/gpt/
gpt_exporter/providers/discord/
```

The core provider registry itself imports no concrete provider, but `gpt_exporter/application.py` still explicitly composes ChatGPT and Discord. That is transitional coupling and is intentionally documented as next-milestone work rather than treated as solved.

## Canonical provider boundary

Providers implement the canonical source boundary in `gpt_exporter.core` and normalize source data into:

```text
CanonicalConversation
CanonicalMessage
CanonicalAsset
```

The canonical model contains cross-provider concepts only. Provider-only fields remain provider metadata and must not become required shared fields merely because one service exposes them.

The current minimal `ConversationProvider` protocol supplies:

```text
descriptor
discover(source)
normalize(source)
```

That contract is intentionally small. The future package architecture will require a richer capability/registration layer for workspace defaults, collection, archive actions, regeneration, optional remote operations, CLI dispatch and compatibility/version negotiation without making every provider implement every capability.

## Shared application layers

The intended shared stack is:

```text
CLI -------------------+
                       |
GUI -------------------+--> shared application/workflows
                               |
                               v
                     provider capability contracts
                               |
                               v
                        installed providers
```

The GUI is not the engine. Provider and archive behavior must remain callable independently of Tkinter, and GUI/CLI must invoke the same underlying operations.

Shared code owns, or is the intended owner of:

- canonical conversation/message/asset representation;
- canonical serialization;
- shared SQLite indexing and FTS search;
- canonical Markdown rendering and shared DOCX generation;
- Browser and workspace shell;
- categories, tags and work-project organization;
- archive workflow/process/progress windows;
- persistent workflow logs;
- provider registry/discovery infrastructure;
- application lifecycle and provider-neutral CLI dispatch;
- explicit-root shared path abstractions.

A provider owns source/service-specific behavior such as:

- service/source discovery and acquisition;
- browser collector resources or native import adapters;
- provider export validation;
- source-schema parsing and visibility/history rules;
- normalization to the canonical model;
- provider-specific identifiers and metadata;
- provider-specific archive policy that cannot safely be generalized;
- provider-specific default workspace proposal;
- provider-specific remote-service operations;
- provider-specific historical migrations and resources.

Provider code should not clone a workflow or UI merely because the data source differs. When ChatGPT and Discord need the same lifecycle, that lifecycle belongs in the shared layer and provider capabilities feed it.

## Current package ownership

A simplified view of the current tree is:

```text
gpt_exporter/
├── application.py                 # shared shell, but still explicit provider composition
├── workspaces.py                  # provider-neutral workspace catalog/model
├── core/
│   ├── model.py                   # canonical provider-neutral model
│   ├── provider.py                # provider protocol/descriptor
│   ├── provider_registry.py       # registry with no concrete-provider imports
│   └── serialization.py           # canonical durable JSON/XZ
├── index/                         # shared canonical SQLite/indexing
├── export/                        # shared Markdown/DOCX rendering
├── ui/
│   ├── archive_workflow.py        # shared collector/archive lifecycle UI
│   ├── browser/                   # shared Browser
│   └── ...                        # shared workspace/remote-deletion shells
└── providers/
    ├── gpt/                       # ChatGPT-specific source/archive behavior
    └── discord/                   # Discord-specific source/archive behavior
```

Historical repository-root scripts remain compatibility launchers where existing commands must continue to work. They should not regain provider schema/business logic.

## Shared archive workflow

`gpt_exporter/ui/archive_workflow.py` is the reference pattern for provider-neutral UI composition.

The shared UI owns:

- the three-step collection/archive dialog;
- export waiting/detection lifecycle;
- background execution;
- progress rendering;
- persistent logs;
- success/failure window behavior;
- Browser refresh completion handling.

Providers supply an `ArchiveWorkflowSpec` plus action methods for service-specific operations. New providers should extend this contract or its successor instead of implementing a separate archive window.

## ChatGPT source flow

The ChatGPT provider owns ChatGPT-specific acquisition and normalization:

```text
Authenticated ChatGPT tab
        |
        v
providers/gpt/resources/collector
        |
        v
ChatGPT browser export
        |
        v
providers/gpt importer/pipeline
        |
        v
ChatGPTProvider -> CanonicalConversation
```

Provider-native compatibility paths remain provider-owned. Once normalized, shared indexing/rendering/browser infrastructure should be used wherever possible.

## Discord source flow

Discord is the second concrete provider and follows the same shared application model:

```text
Authenticated Discord DM
        |
        v
providers/discord/resources collector
        |
        v
Discord browser export
        |
        v
providers/discord archive/history/asset logic
        |
        v
DiscordProvider -> CanonicalConversation
        |
        +--> shared index / Browser
        +--> shared Markdown/DOCX renderer
```

Discord-specific history completeness, cumulative message merge, safe remote deletion and DM naming remain provider responsibilities. The workflow/progress UI and generic renderer are shared.

See `DISCORD_PROVIDER.md` for the provider behavior and archive format.

## Provider-neutral SQLite schema

The shared SQLite model stores provider metadata generically in `conversation_provider_metadata` instead of adding one column per service-specific field.

The current index schema has advanced beyond the historical v5 provider-extraction milestone; documentation and tests should refer to the active schema version rather than assuming the old v5 baseline. Provider-specific metadata must continue to fit the generic metadata mechanism without requiring a shared-schema change for every new provider.

This remains a strict architectural requirement for future packages.

## Archive authority and derived outputs

Across providers, preserve the distinction between durable source/canonical data and derived presentation/index artifacts.

For ChatGPT, historical preservation rules established by the frozen v2.7 line remain authoritative.

For Discord, the current archive preserves a byte-exact compressed raw collector snapshot plus a cumulative canonical conversation. DOCX and SQLite are derived/rebuildable. Multipart DOCX does not create multiple logical conversations; it creates several derived views of one canonical conversation.

## Discord multipart DOCX

Large Discord DMs are split by message density, not by page count or file size.

Current rule:

```text
threshold = 1000 messages
sparse pre-dense years -> one historical range when useful
dense year -> semester if semester count < threshold
otherwise -> quarter
minimum granularity -> quarter
```

The validated 6,674-message Gadget MCS ↔ Littleloulita archive produces:

```text
2022-2025 : 37
2026Q1    : 1872
2026Q2    : 2550
2026Q3    : 2215
```

The Browser still has one conversation row and records the latest part as the primary `docx_path`. Deferred Browser multipart navigation and incremental-part regeneration are recorded in `TODO.md`.

## Remote deletion boundary

Remote deletion is a provider capability, not a shared assumption.

The shared application owns the safety workflow and confirmation surface. A provider that supports remote deletion supplies the service-specific dry run and execution mechanics. Discord is the first implementation.

The local canonical archive is not deleted by the remote operation. Discord deletion is permitted only after the dry-run candidate set is proven covered by the local archive; unsafe/incomplete coverage blocks the action rather than offering an override.

## Compatibility facades

Historical public imports and root scripts may remain while migration is in progress, subject to two rules:

1. they contain no provider schema/business logic that should live in a provider package;
2. generic package imports must not eagerly require a concrete provider.

Compatibility code is not justification for adding new concrete-provider coupling.

## Current removal resilience versus future packageability

Existing tests already prove important parts of provider-removal resilience, especially for the shared core. That is necessary but not sufficient for the next milestone.

The stronger future acceptance test is literal application composition:

```text
remove ChatGPT provider -> app/CLI continue with Discord
remove Discord provider -> app/CLI continue with ChatGPT
remove all providers -> shared application imports/startup remain valid
add unknown provider package -> discovered without main-app source edit
```

Today `application.py` still contains explicit provider imports/conditionals for registration, default workspaces, legacy launchers, workspace argument translation and workspace action creation. Those must move behind dynamic discovery/capabilities before provider packageability can be declared complete.

## Future independent provider development

The package contract must eventually permit provider repositories such as:

```text
export-provider-chatgpt
export-provider-discord
export-provider-linkedin
```

A new provider repository should consume a stable shared provider API/SDK, run its own contract tests, and produce an installable artifact without modifying the exporter repository just to register the provider.

The exact artifact format is deliberately undecided. See `PROVIDER_PACKAGE_ARCHITECTURE.md`.

## Future product identity

After provider independence/packageability is fully implemented and validated, the project is intended to be renamed **Multi Social Network Explorer (MSNE)**. The rename is a later milestone and should not be mixed into the provider-contract refactor.

## Preservation/versioning rule

The v2.7 ChatGPT frozen archive baseline remains historical preservation evidence. Subsequent multi-provider refactors must preserve established archive semantics unless an explicit migration, changelog entry and rollback strategy say otherwise.

For current development state and next steps, see `HANDOVER_PROVIDER_PACKAGING.md` and `TODO.md`.
