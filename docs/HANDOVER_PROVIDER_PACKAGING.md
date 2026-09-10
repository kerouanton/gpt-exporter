# Handover — provider packaging and MSNE preparation

Date: 2026-09-10

This handover is intended to let a new development conversation continue the next architectural milestone without reconstructing the recent Discord/provider work from chat history.

## Immediate objective

First consolidate and merge the current stacked provider/Discord work into a stable milestone. Then start a separate provider-packaging refactor whose goal is to make providers independently developed, independently installable and dynamically discovered.

Do not start by renaming the product. The future rename to **Multi Social Network Explorer (MSNE)** should follow successful provider-independence validation.

## Current branch and PR stack

The active development branch at handover is:

```text
feat/discord-multipart-docx
```

It is stacked on the current Discord/provider refactor chain:

```text
#72 refactor/shared-archive-workflow
    ↓
#73 feat/discord-cumulative-dm-archive
    ↓
#74 feat/shared-remote-deletion
    ↓
#75 feat/discord-multipart-docx
```

At the time of this handover all four PRs are still open and intentionally stacked. Before merging, re-check current CI/status and mergeability rather than relying on old snapshots.

PR purposes:

- **#72 — Unify Archive New Conversations workflow across providers:** shared `ArchiveWorkflowDialog` / processing window, common lifecycle, provider action contract, persistent logs.
- **#73 — Preserve cumulative Discord DM history across recaptures:** merge by stable message ID, deleted/edit markers, conservative cumulative archive behavior.
- **#74 — Add shared remote deletion safety workflow:** provider-neutral safety UI/plan, Discord implementation, archive coverage checks, dry run, pinned destructive action, no local archive deletion.
- **#75 — Split dense Discord DOCX exports by time period:** density-based multipart DOCX while keeping one canonical conversation and one Browser row.

## Discord state validated in real use

The Discord browser collector has been exercised against real direct-message archives. Important behavior now in place includes:

- locale-independent current-user detection;
- explicit full-history evidence before tombstoning remotely missing messages;
- cumulative canonical history keyed by message ID;
- raw collector snapshot preservation;
- canonical author display names and compact shared chat rendering;
- author avatars used only in the participant header, not repeated in message bodies;
- symmetric human DM titles/filenames;
- shared archive workflow and persistent processing logs;
- safe remote deletion of archived own messages after dry-run coverage verification;
- DOCX regeneration backlog support;
- density-based multipart DOCX output for large conversations.

The principal real multipart validation conversation contained 6,674 messages and produced:

```text
2022-2025 : 37 messages
2026Q1    : 1,872 messages
2026Q2    : 2,550 messages
2026Q3    : 2,215 messages
```

Observed Word document sizes/page counts were approximately:

```text
2022-2025 : 11.8 MB / 17 pages
2026Q1    : 84.4 MB / 391 pages
2026Q2    : 128.4 MB / 669 pages
2026Q3    : 60.8 MB / 1,181 pages
```

This confirmed that page count is not a useful proxy for DOCX weight; media density varies strongly. Keep the message-density split policy rather than changing to page/byte thresholds.

The split rule is:

- density threshold: 1,000 messages;
- sparse years before the first dense year may be merged into one historical range such as `2022-2025`;
- dense years use semester buckets where each semester is below threshold;
- otherwise split the dense semester into quarters;
- quarter is the minimum granularity;
- exactly 1,000 escalates because the comparison is strictly `< 1000`;
- undated messages must never be dropped.

A single-part conversation keeps the legacy unsuffixed DOCX name. Multipart conversations use suffixes such as ` - 2026Q3.docx`.

The Browser remains one logical row per Discord channel/conversation. The archive records the latest part as `docx_path` so normal open-DOCX behavior opens the current/latest part.

## Participant header behavior

The validated participant header now uses display names only when available:

```text
[avatar] Gadget MCS ↔ [avatar] Littleloulita
```

Fallback order is display name, then username, then stable ID.

Empty Discord participant placeholder records are filtered and must not render as `Unknown participant`.

## Deferred multipart TODOs

Do not expand scope during consolidation. These are explicitly deferred and recorded in `docs/TODO.md`:

- Browser UI for selecting/opening any DOCX part while retaining one conversation row;
- regeneration of only changed/current multipart periods instead of all parts;
- fuller multipart result/progress reporting;
- cleanup of path-resolution helpers that still assume one unsuffixed DOCX where necessary.

Do not implement `Regenerate All DOCX…`; manual deletion plus `Regenerate Missing DOCX…` is the accepted maintenance workflow.

## Existing provider-neutral foundation

The repository is already significantly provider-neutral:

```text
gpt_exporter/core/
    model.py
    provider.py
    provider_registry.py
    serialization.py

gpt_exporter/index/
gpt_exporter/export/
gpt_exporter/ui/
gpt_exporter/workspaces.py

gpt_exporter/providers/gpt/
gpt_exporter/providers/discord/
```

`ConversationProvider` currently defines the minimal canonical boundary: descriptor, discovery and normalization. `ProviderRegistry` itself imports no concrete providers.

The shared archive workflow under `gpt_exporter/ui/archive_workflow.py` is an important architectural pattern to preserve: the UI owns the dialog/lifecycle while provider actions supply service-specific capabilities and text.

The Browser/shared workspace shell is also moving in this direction.

## Important remaining coupling

The main application is **not yet dynamically provider-packageable**.

`gpt_exporter/application.py` still explicitly knows the current provider names. In particular it currently contains concrete ChatGPT/Discord logic for:

- importing and registering provider classes;
- constructing default workspaces;
- legacy provider GUI launchers;
- translating workspace arguments;
- choosing provider-specific workspace action classes.

These conditionals/imports are the clearest evidence that the next milestone is still required. Do not claim provider packaging is already complete merely because the providers live in separate directories.

The target architecture is specified in `docs/PROVIDER_PACKAGE_ARCHITECTURE.md`.

## Provider-packaging target

The core requirement is stronger than folder separation:

> Adding or removing a provider must not require a source-code change in the main exporter.

A provider should eventually be distributable independently (the final format may be a ZIP, Python distribution, entry-point package, application-local plugin directory, or another mechanism). Installing/uninstalling that package should make the provider appear/disappear automatically.

The dependency direction must be:

```text
provider package  ---> shared provider API/SDK + engine
shared engine     -X-> concrete provider package
```

The application must be able to start with zero providers installed. With one provider removed, every other installed provider must continue to work.

## UI requirement

There must be one common UI/workflow model, not one application per provider.

Shared code owns the Browser, workspace shell, workflow windows, processing/progress UI, persistent logs, common menus/lifecycle and other generic presentation. Providers advertise capabilities and supply provider-specific data/text/resources; they must not require changes to the shared UI for each new provider.

Provider-specific legacy GUIs may remain temporarily for compatibility during migration, but they are not the target architecture.

A future `export-provider-linkedin` must be able to plug into the same UI without adding `LinkedIn` branches to the main repository.

## CLI requirement

Everything significant must work independently of Tkinter.

Business operations belong in provider/shared library APIs. GUI and CLI are peers over those APIs. A provider is incomplete if collection/archive/normalization/regeneration or other fundamental operations can only be triggered through its GUI callbacks.

The future provider contract therefore needs to describe capabilities callable by application code and CLI code, not widget implementations.

## Independent provider repositories

The architecture should permit a new development session to work in a dedicated repository such as:

```text
export-provider-linkedin
```

without changing the main exporter repository simply to register or expose LinkedIn.

That repository should depend on a stable shared provider API/SDK, run provider-contract tests, and produce its own installable artifact. ChatGPT and Discord can be split into dedicated repositories after the package contract is stable and proven.

## Suggested implementation sequence for the next conversation

1. **Do not refactor immediately.** Inspect the post-merge `main`, current tests and packaged Windows build behavior first.
2. Define a small provider package manifest/descriptor and capability model, including a provider API compatibility version.
3. Separate provider discovery from `application.py`; the application must enumerate installed packages without naming them.
4. Move default-workspace proposals behind provider registration metadata/capabilities.
5. Move workspace actions and CLI dispatch behind capability objects rather than `if provider_id == ...` branches.
6. Keep all common UI in the shared layer; provider packages provide data/actions only.
7. Add a synthetic third provider used only by tests to prove zero-touch discovery.
8. Add physical-removal tests for GPT, Discord, both, and all providers.
9. Validate dynamic discovery in the Windows `onedir` package, not only in a source checkout.
10. Once stable, decide the independent provider distribution/repository mechanism and migrate ChatGPT/Discord incrementally.
11. Only after this is complete, prepare the separate MSNE rename milestone.

Do not overdesign the plugin API before identifying the actual capabilities already shared by GPT and Discord. Extract the contract from proven behavior.

## Acceptance definition

The provider-packaging milestone is not complete until all of these are true:

```text
- remove ChatGPT package -> app/CLI still work with Discord
- remove Discord package -> app/CLI still work with ChatGPT
- remove all providers -> shared application imports/startup remain valid
- add unknown synthetic provider -> discovered with no core edit
- synthetic provider works through shared CLI/library paths
- synthetic provider appears through the same shared UI/workflow shell
- no main/shared module names concrete providers as required dependencies
- Windows packaged build obeys the same install/remove/discover behavior
```

## Merge/consolidation warning

The current branch stack contains historical/stale tests that have at times failed for reasons unrelated to the latest multipart feature. Do not represent CI as globally green without checking the current runs. During consolidation, reconcile obsolete test expectations with the now-intended architecture rather than weakening current safety behavior merely to satisfy old tests.

The user is collecting one or two additional Discord conversations as final real-world validation. Incorporate any resulting defects before declaring the current Discord milestone frozen.
