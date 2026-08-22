# v7 frozen version manifest

The code package containing this file is **gpt-exporter v7**, frozen on **2026-08-17** after complete validation on the target Windows archive. v7 branches directly from the v6 frozen baseline and preserves its canonical archive invariants.

## Release identity

- Project: `gpt-exporter` / ChatGPT Archiver
- Frozen release: **v7**
- Freeze date: **2026-08-17**
- Reference archive filename: `gpt-exporter-v7.zip`
- Exact package-source hashes: `SOURCE_SHA256SUMS.txt`
- Previous frozen baseline: **v6**

`SOURCE_SHA256SUMS.txt` identifies every source/documentation file in the release except the checksum file itself. The distributable ZIP hash is published next to the release artifact because embedding the ZIP hash inside the ZIP would be self-referential.

## Frozen architectural invariants

Canonical durable data remains:

```text
downloads\*.json.xz
assets\*
```

DOCX, Markdown, manifests, reports, indexes, and provenance catalogs are derived/rebuildable. Normal operation is cumulative and non-destructive: existing assets are never pruned merely because they are absent from a later browser bundle. Asset collection remains deliberately broad.

The stable join key is the ChatGPT `file_id` embedded in archived filenames. DOCX is a readable representation rather than the source of truth. Unsupported image formats may be normalized in memory for DOCX embedding, but source assets are never rewritten for compatibility.

## v7 acceptance record

The frozen code was validated on the target Windows installation with:

```text
py archive_chats.py --convert-only
```

Final rebuild result:

```text
Requested : 80
Converted : 80
Skipped   : 0
Failed    : 0
```

Final cumulative asset audit:

```text
Physical asset files        : 1610
Unique local asset IDs      : 1530
DOCX files scanned          : 80
Rendered asset IDs found    : 1455
Unreferenced local assets   : 120
Referenced but local-missing: 45
Duplicate local asset IDs   : 45
  byte-identical            : 45
  content-conflicting       : 0
  unreadable                : 0
Unidentified asset files    : 0
```

Duplicate kinds:

```text
attachment_filename_variant : 28
dictation_mirror             : 9
image_mirror                 : 8
```

Final unreferenced classification:

```text
dictation_source_inactive_or_hidden : 1
inactive_branch_only                 : 13
internal_image_inspection            : 72
tool_source_or_internal              : 34
```

The 45 local-missing assets are real visible user attachments preserved as explicit missing-attachment markers in the derived documents. Their absence is not hidden or substituted.

The remaining 12 historical sandbox-link occurrences with several non-identical same-basename local candidates were inspected against canonical conversation JSON. Six are generic/generated `README.md` paths without a reliable path-to-file-ID mapping; six are network-rescue script paths where two or three distinct revisions with the same basename exist in the same conversation. v7 intentionally leaves these links non-clickable rather than selecting a guessed target.

## v7 feature delta from v6

- restores visible generated-image tool results in DOCX/Markdown while continuing to exclude hidden technical duplicates;
- links original dictation `.m4a` audio next to the visible transcript;
- explicitly renders visible attachments that are referenced by conversation JSON but physically missing locally;
- sanitizes XML-incompatible text after Markdown parsing as well as before DOCX insertion;
- classifies model-side `container.open_image` outputs as `internal_image_inspection` and keeps them out of user-facing exports;
- audits real DOCX hyperlink relationships into `assets\...` as rendered references;
- resolves same-basename sandbox candidates only when they are unique or byte-identical;
- hashes duplicate local Asset IDs and reports content conflicts without deleting any copy.

## Preservation rule for future work

Any future v8+ work should branch conceptually from this v7 frozen release. Changes that alter canonical data, cumulative behavior, asset collection breadth, deletion policy, visible-role semantics, or local-link semantics must be explicit in `CHANGELOG.md` and include a migration/rollback plan.

## Historical baseline

The prior frozen reference was v6, also frozen on 2026-08-17. v7 retains v6's canonical `.json.xz + assets` architecture and broad collector; its changes are confined to derived export behavior, conservative hyperlink recovery, and diagnostics.
