# Provider package architecture target

Status: **next architectural milestone, not yet fully implemented**.

GPT Exporter has already moved from a ChatGPT-only codebase to a provider-neutral core with ChatGPT and Discord provider directories. The next milestone is stronger: providers must become independently developed, independently installable packages that the main application discovers dynamically.

This document defines that target before implementation begins.

## Goal

The main application must not know that ChatGPT, Discord, LinkedIn, or any other concrete provider exists.

A provider must be removable from the installed `providers/` area without breaking the exporter. A new provider must be addable without editing the exporter source. The distribution format is intentionally unspecified here: a ZIP unpacked below `providers/`, a Python package, an entry-point based package, or another mechanism may be selected later. The architectural contract matters more than the container format.

The intended end state is:

```text
shared application / CLI / GUI
            |
            v
provider-neutral contracts + discovery
            |
            +--> installed ChatGPT provider package
            +--> installed Discord provider package
            +--> installed LinkedIn provider package
            +--> ...
```

The dependency direction is one-way:

```text
provider package  ------>  shared core/SDK
shared core       -X---->  concrete provider package
```

## Non-negotiable invariants

### 1. Providers are optional

The application must start with zero providers installed. It may report that no usable provider/workspace is available, but importing or starting the shared application must not fail because `providers/gpt`, `providers/discord`, or any other concrete package is absent.

Removing only ChatGPT must leave Discord usable. Removing only Discord must leave ChatGPT usable.

### 2. Providers are discovered, not hard-coded

Adding a provider must not require edits to central tables such as:

```text
if provider_id == "gpt": ...
if provider_id == "discord": ...
```

The current `gpt_exporter.application` still contains explicit imports, workspace defaults, launchers, provider argument translation, and workspace-action construction for the two known providers. That is transitional composition code and is a primary target of the next refactor.

A provider package must expose enough metadata/capabilities for discovery and registration without a source change in the main application.

### 3. One shared UI and one shared workflow model

The user interface must not be reimplemented for every provider.

The Browser, workspace shell, archive workflow window, processing/backlog window, progress reporting, persistent logs, maintenance actions, and common lifecycle belong to shared application/UI code. Providers supply capabilities, data and provider-specific text where necessary; they do not supply a different application experience.

The shared archive workflow already demonstrates the intended direction through `ArchiveWorkflowSpec` and `ArchiveWorkflowActions`: the UI owns the window and lifecycle while the provider implements service-specific operations.

Future provider packages must extend this pattern rather than introducing provider-owned duplicate windows.

### 4. CLI and GUI are peers over the same engine

No important archive behavior may exist only in Tkinter callbacks.

Collection, validation, normalization, archive update, asset handling, DOCX generation, indexing, regeneration, remote actions and other provider capabilities must be callable as library/API operations. The GUI and CLI are clients of those operations.

Target layering:

```text
CLI -------------------+
                       |
GUI -------------------+--> shared application/workflows
                               |
                               v
                       provider capability contract
                               |
                               v
                         provider package
```

A provider that works only through the GUI does not satisfy the package contract.

### 5. Shared facilities stay outside providers

The following are shared responsibilities and must not be cloned into provider packages merely to make them independent:

- canonical conversation/message/asset model;
- canonical serialization contracts;
- shared SQLite index and FTS infrastructure;
- Browser and workspace shell;
- common archive-processing/progress/log UI;
- common Markdown/DOCX rendering machinery;
- shared organizational metadata such as projects/categories/tags;
- provider registry/discovery mechanism;
- application lifecycle and provider-neutral CLI dispatch;
- common resource/path abstractions where semantics are genuinely provider-neutral.

Provider-specific policy may feed these facilities through capability contracts without forking them.

### 6. Provider packages own only source-specific behavior

A provider package may own:

- provider descriptor and version;
- source/service discovery;
- browser collector resources or external import adapters;
- validation of provider exports;
- source-schema parsing;
- normalization to the canonical model;
- provider-specific identifiers and metadata;
- provider-specific archive policy that cannot be generalized safely;
- provider-specific default workspace proposal;
- provider-specific remote-service operations;
- provider-specific migrations;
- provider-specific resources and tests.

This boundary must be reviewed critically. If ChatGPT and Discord implement materially identical workflow/UI code, that is evidence the code belongs in the shared layer.

## Provider package contract to design

The existing minimal `ConversationProvider` contract exposes a descriptor, `discover()` and `normalize()`. That is useful but insufficient for independently packaged full providers.

The next milestone should design a richer package/registration contract covering capabilities such as:

```text
identity / descriptor
compatibility / API version
provider factory
workspace defaults
source discovery / collection
export validation
normalization
archive/update operation
regenerate derived outputs
optional remote-service actions
provider resources
CLI commands/capabilities
UI-facing capability metadata, not provider-owned UI
```

The contract should prefer optional capabilities over a monolithic interface. A provider that cannot perform remote deletion, for example, should simply not advertise that capability.

The package must also declare compatibility with a stable provider API/SDK version so an incompatible plugin can be rejected cleanly instead of failing during arbitrary imports.

## Discovery and packaging

Do not choose the packaging mechanism merely because the prototype currently uses Python subdirectories.

The implementation phase should evaluate at least:

- packages placed below a dedicated provider directory and discovered by manifest;
- Python package entry points;
- separately installed Python distributions;
- an application-local plugin directory suitable for a Windows `onedir` build;
- a simple distributable archive that installs/unpacks one provider package.

Whichever mechanism is chosen must preserve the invariants above and work with the packaged Windows application.

The desired operational experience is conceptually:

```text
install/remove provider package
        |
        v
start application
        |
        v
discovery validates package + API compatibility
        |
        v
provider appears/disappears automatically in GUI and CLI
```

## Independent repositories

A major acceptance criterion is organizational, not just technical.

It must be possible to create a repository such as:

```text
export-provider-linkedin
```

and develop it without modifying or checking out the main exporter repository except as a dependency/SDK consumer.

The provider repository should be able to run its own provider-contract tests and produce an installable provider artifact. Development of a new provider must not require a coordinated source commit in the main application simply to register its name, create its UI, add a launcher, or add `if provider_id == ...` branches.

ChatGPT and Discord may later be split into their own repositories once the contract is stable; that split is a consequence of the architecture, not the first implementation step.

## Acceptance tests for the milestone

The architecture is complete only when tests prove behavior, not just directory layout.

Required scenarios:

1. Build/run shared application with both current providers installed.
2. Physically remove the ChatGPT provider package; application starts and Discord remains usable.
3. Restore ChatGPT, physically remove Discord; application starts and ChatGPT remains usable.
4. Remove all providers; shared imports and startup remain intact and the absence of providers is handled explicitly.
5. Add a synthetic provider package that was not named in main-application source code; it is discovered automatically.
6. Exercise that synthetic provider through shared library/CLI paths.
7. Exercise it through the same shared GUI/workflow shell without provider-specific GUI code in the main repository.
8. Verify no shared module imports a concrete provider as a runtime prerequisite.
9. Verify provider-specific metadata does not require shared schema changes.
10. Verify a packaged Windows build can discover/remove/add provider packages according to the selected distribution model.

## Relationship to the future MSNE rename

After this milestone is complete and validated, the name `gpt-exporter` will no longer describe the architecture accurately. The planned product/repository identity is:

**Multi Social Network Explorer (MSNE)**

The rename should happen after provider packaging is real, not before. That makes the rename an architectural milestone rather than a cosmetic one and follows the same broad product idea as Multi Radio Playlist Explorer: one shared explorer, multiple independently supplied sources.

The future rename is deliberately out of scope for the provider-packaging implementation itself. Preserve compatibility first, prove the provider boundary, then rename the application/package/repository in a separate controlled step.
