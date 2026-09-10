# Discord provider

Status: guided browser collection, cumulative canonical archive, shared Browser/workflow integration, safe remote deletion, and density-based multipart DOCX for large DMs.

Discord is the second concrete provider. Service-specific behavior lives below `gpt_exporter/providers/discord`, while the archive workflow UI, Browser, canonical model, index and generic rendering facilities are shared.

## Normal workflow

Selecting/using the Discord workspace follows the same shared archive workflow used by other providers.

1. Open Discord in the normal authenticated browser session and select the DM to archive.
2. Start **Archive New Conversations…**. The provider's collector JavaScript is copied to the clipboard and the shared workflow starts watching Downloads.
3. In Discord press **F12**, open **Console**, paste and run the collector.
4. The provider detects the new `discord-dm-export-v15_*.json`, validates it, normalizes it, merges it into cumulative history, archives assets/JSON, generates DOCX output, updates the shared SQLite index, and refreshes the Browser.

The application does not read Discord tokens, passwords, cookies, or browser profiles.

## Collector and history completeness

Discord uses a virtualized message scroller, so reaching a stable scroll position is not sufficient evidence that the beginning of history was reached.

The collector records explicit diagnostics such as whether the beginning marker was observed and whether the final capture satisfies the complete-history conditions. Tombstone/deletion inference is deliberately conservative: remotely missing messages are marked deleted in cumulative history only when the new capture provides sufficient full-history evidence.

A partial/unverified collector run must not cause thousands of historical messages to be falsely marked deleted or silently shrink the canonical archive.

## Current-user detection

The collector detects the logged-in Discord user without depending solely on English UI labels. Locale-independent/fallback detection was added and validated with both sides of the same real DM during debugging.

The `current_user` record is used to classify message ownership and enrich participant identity, but cross-account collection of the same DM is not a normal operating requirement.

## Archive layout

The provider owns its default workspace root:

```text
%USERPROFILE%\Documents\Discord Archive\
├── assets\
│   ├── attachment\...
│   ├── dictation\...
│   ├── image\...
│   └── external\...
├── downloads\
│   ├── Discord DM <local> ↔ <peer> <channel-id>.raw.json.xz
│   └── Discord DM <local> ↔ <peer> <channel-id>.canonical.json.xz
├── reports\
├── Discord DM <local> ↔ <peer> <channel-id>.docx
│   OR multipart derived DOCX files
└── conversations-index.sqlite
```

Raw and canonical XZ files are deliberately co-located in `downloads/` but have explicit suffixes and different roles:

- `*.raw.json.xz` is the latest collector snapshot, compressed while preserving the original collector payload semantics;
- `*.canonical.json.xz` is the cumulative provider-neutral conversation used as the durable normalized archive source.

Historical layouts using a separate `raw/` directory or older names are migrated/handled by provider compatibility code. The canonical index ignores raw snapshots.

DOCX and SQLite are derived/rebuildable.

## Cumulative DM history

Recaptures merge by stable Discord message ID rather than replacing the canonical history wholesale.

The merge behavior preserves:

- newly seen messages;
- previously archived messages absent from a later partial capture;
- edit detection for same-ID content changes;
- deletion tombstones when full-history evidence safely supports them;
- reappearance of a previously tombstoned message.

Canonical message content is retained; derived rendering may add discreet `(edited)` / `(deleted)` presentation markers where appropriate.

## Canonical mapping

- current user's messages: `role = "user"`;
- other participant's messages: `role = "other"`;
- unresolved authors: `role = "unknown"`;
- Discord display names are preserved as `author_name`;
- attachment/media URLs become canonical assets;
- replies, reactions, mentions, content types and Discord diagnostics remain provider/message metadata.

The shared chat renderer uses real author names rather than presenting Discord as a user/assistant exchange.

## Human naming

DM titles and artifact stems are symmetric and human-readable:

```text
Discord DM Gadget MCS ↔ Littleloulita 994497416583708703
```

The stable channel ID remains part of filenames for unambiguous identity.

One Discord channel remains one logical Browser conversation even if exceptional debugging creates artifacts from both account orientations.

## DOCX participant header

Each derived Discord DOCX starts with one compact participant header using avatars when available and display names as the preferred visible labels:

```text
[avatar] Gadget MCS ↔ [avatar] Littleloulita
```

Username is a fallback only when a display name is unavailable; stable ID is the final fallback. Empty placeholder participant records are ignored and must not create an `Unknown participant` token.

Per-message avatars are intentionally omitted from the body to keep large documents practical. Author names remain grouped in the shared chat rendering.

## Density-based multipart DOCX

One very large DOCX became impractical, so Discord DMs can now produce multiple derived DOCX parts while keeping **one raw snapshot, one canonical conversation, and one Browser row**.

The split policy is based on message density:

```text
threshold = 1000 messages
```

Rules:

- sparse years before the first dense year may be merged into one historical range;
- a dense year uses semester parts when a semester remains below 1,000 messages;
- otherwise the dense semester is split into quarters;
- quarter is the minimum granularity;
- the test is strictly `< 1000`, so exactly 1,000 escalates;
- undated messages are preserved.

The validated 6,674-message Gadget MCS ↔ Littleloulita conversation produces:

```text
Discord DM Gadget MCS ↔ Littleloulita 994497416583708703 - 2022-2025.docx
Discord DM Gadget MCS ↔ Littleloulita 994497416583708703 - 2026Q1.docx
Discord DM Gadget MCS ↔ Littleloulita 994497416583708703 - 2026Q2.docx
Discord DM Gadget MCS ↔ Littleloulita 994497416583708703 - 2026Q3.docx
```

with message counts 37, 1,872, 2,550 and 2,215 respectively.

A conversation whose plan has only one part keeps the historical unsuffixed DOCX filename.

The Browser currently records the latest part as the primary `docx_path`. A future part picker and changed-period-only regeneration are explicitly deferred in `TODO.md`.

## Missing-DOCX regeneration

`Regenerate Missing DOCX…` rebuilds derived Discord DOCX output from the existing archived raw/canonical data. This is the accepted maintenance/test path after manually deleting DOCX files.

There is intentionally no `Regenerate All DOCX…` command planned.

## Remote deletion safety

Discord is the first provider implementing the shared remote-deletion capability.

The operation is intentionally conservative:

1. the conversation must already exist in the local archive;
2. a dry run collects candidate own-message IDs from the exact DM;
3. every candidate must be present in the local canonical archive;
4. incomplete/unsafe coverage blocks execution with no override;
5. the user explicitly confirms the safe candidate set;
6. destructive execution is pinned to the exact channel, current Discord user and dry-run message IDs;
7. HTTP 429 responses are retried;
8. the local canonical archive and derived documents are not deleted by the remote operation.

This mechanism does not extract Discord authentication tokens or cookies.

## Native Discord data packages

The earlier native data-package JSON/CSV adapter remains a compatibility ingestion path. Guided browser collection is the normal workflow because it captures the currently displayed DM directly.

## Architectural boundary

Discord-specific collection, schema interpretation, history safety, naming, remote-service actions and migrations remain provider responsibilities.

The Browser, canonical model, shared index, shared DOCX renderer, workflow/progress/log windows and application shell should remain provider-neutral. The next milestone will make provider discovery/package installation independent as described in `PROVIDER_PACKAGE_ARCHITECTURE.md`.
