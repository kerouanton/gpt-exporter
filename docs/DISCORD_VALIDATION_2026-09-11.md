# Discord validation checkpoint — 2026-09-11

This checkpoint records the end-to-end validation state of the Discord provider before the next provider-packaging milestone.

## Scope validated on real archive data

The Discord archive corpus was completed successfully, including ordinary 1:1 DMs, very large DMs, very short DMs, empty DMs, unresolved/deleted peers, and multi-participant Group DMs.

Validated behavior:

- ordinary 1:1 DMs archive into one cumulative canonical conversation keyed by Discord channel ID;
- large DMs keep one raw/canonical conversation and can render density-based multipart DOCX output;
- short DMs whose message pane is not actually scrollable are still collected;
- truly empty DMs terminate cleanly instead of looping during enrichment;
- a DM with zero canonical messages can legitimately have no conversation date and no DOCX output;
- unresolved/deleted peers can use the Discord page title as a human naming fallback without inventing a stable user ID;
- Browser/index naming for 1:1 DMs is normalized to `A ↔ B`;
- Group DMs are detected from distinct real participant identities rather than trusting the legacy collector `type` field alone;
- named Group DMs use the visible group name as the Browser title and artifact label;
- unnamed Group DMs fall back to a compact `A · B · C` participant label;
- Group DM DOCX rendering keeps the multi-participant avatar/name header and preserves system events such as group renames or membership changes;
- Browser categories distinguish `Discord Direct Message` from `Discord Group DM` and remain mutually exclusive after reindexing;
- remote deletion is intentionally disabled for Group DMs in this checkpoint;
- all currently known Discord DMs and Group DMs in the validation archive were successfully archived.

## Multipart reference validation

The real Gadget MCS ↔ Littleloulita DM contains 6,674 messages and validates the current density policy:

- 2022-2025: 37 messages, 17 pages, approximately 11.8 MB;
- 2026Q1: 1,872 messages, 391 pages, approximately 84.4 MB;
- 2026Q2: 2,550 messages, 669 pages, approximately 128.4 MB;
- 2026Q3: 2,215 messages, 1,181 pages, approximately 60.8 MB.

This confirms that page count is not a useful proxy for DOCX weight; the current split remains message-density based.

## Small/edge-case corpus

Representative real cases used during validation:

- `natsfr`: very small normal DM; validated non-scrollable message-pane collection;
- `Warper`: human-visible DM with no actual conversation messages; canonical Browser count correctly remains zero;
- `Zekah`: history consisting of call/system events with unresolved author identity; peer naming fallback validated through JSON, DOCX and Browser index;
- `Perruche0795`: empty DM with an unresolved/deleted remote account; validated zero-message termination without enrichment loop;
- `la Tanière Orga`: named Group DM; validated group identity, participants, system events, DOCX header and category filtering;
- additional Group DMs with participant-derived and renamed titles were archived successfully after the same rules were applied.

## Remote deletion status

Remote deletion remains validated only for 1:1 DMs and remains conservative: execution is pinned to the exact channel, current account and dry-run candidate IDs, while the local archive is preserved.

Known limitations are intentionally deferred:

- voice-call/system events can match Discord search filters but do not expose a normal Delete Message action;
- ordinary deletable messages can remain in contiguous residual clusters after automated bulk deletion;
- a result such as `deleted_count == authorized_count` proves only execution success for the authorized ID set, not that dry-run candidate discovery was complete.

Representative cleanup observations remain documented in `DISCORD_PROVIDER.md` and `TODO.md` for a later hardening pass.

## Checkpoint boundary

At this checkpoint, Discord archival behavior is considered functionally validated on the user's current archive corpus. The next planned major work is provider discovery/packageability (#76), not further Discord feature expansion.

Before merging the stacked PR chain, the repository-wide automated test suite must also be reconciled with the now-documented behavior and return green on supported Python versions. This document records functional validation; it does not waive CI requirements.
