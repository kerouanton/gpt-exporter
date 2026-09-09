# Shared asset refactor plan

Rollback baseline: `rollback/pre-shared-asset-refactor-2026-09-09`
Baseline commit: `af34a4603870556a87802138ad67534e0f3a3760`

## Goals

1. Make the GPT provider internally consistent for archived assets.
2. Extract provider-neutral asset taxonomy/path helpers.
3. Reuse those helpers from GPT and Discord.
4. Preserve existing archives through conservative migrations.
5. Keep rendering provider-neutral.

## Canonical physical buckets

- `assets/attachment`
- `assets/dictation`
- `assets/image`
- `assets/external`

The semantic `kind` remains more specific than the physical bucket.
Examples: `external-preview`, `author-avatar`, `generated-image`, `attachment`.

## Safety rules

- Never delete or move an existing asset until the destination has been verified.
- Preserve registry compatibility while migrations are in progress.
- Prefer content verification for ambiguous duplicates.
- Keep the rollback branch immutable during this refactor.
- Land the work in reviewable phases rather than one monolithic change.
