# Changelog


## v7 — FROZEN — 2026-08-17

- Freezes the RC6 code as the v7 reference release after a complete Windows rebuild of all 80 archived conversations: 80 converted, 0 skipped, 0 failed.
- Final cumulative audit on the target archive: 1,610 physical asset files, 1,530 unique local Asset IDs, 1,455 rendered Asset IDs, 120 local assets intentionally not rendered, 45 referenced-but-local-missing assets, 45 duplicate local Asset IDs, and 0 unidentified asset files.
- All 45 duplicate Asset IDs are byte-identical: 28 `attachment_filename_variant`, 9 `dictation_mirror`, 8 `image_mirror`; 0 content conflicts and 0 unreadable duplicates.
- Final unreferenced classification: 1 `dictation_source_inactive_or_hidden`, 13 `inactive_branch_only`, 72 `internal_image_inspection`, 34 `tool_source_or_internal`. No unexplained physical orphan remains.
- The remaining 12 non-identical same-basename historical sandbox-link occurrences were reviewed against canonical conversation JSON. Provenance cannot identify one exact local target without guessing, so they deliberately remain non-clickable.
- No canonical `.json.xz` format, asset layout, collection coverage, or deletion policy changed between RC6 and this frozen v7 package. The executable source code is byte-identical to RC6; only release documentation and source-hash manifests were finalized.



## v7 RC6

- Fixes a blind spot in the cumulative asset-reference audit: local assets reached through actual DOCX hyperlink relationships are now counted as rendered references even when the visible paragraph has no separate `Asset ID:` provenance line. This is especially important for historical `sandbox:/mnt/data/...` download links that `export_docx.py` successfully resolves to `assets\...`.
- Extends persistent-Markdown auditing in the same direction by counting local `assets/...` link targets in addition to explicit `Asset ID:` lines.
- Improves ambiguous historical sandbox-link recovery without guessing: when several archived files share the same basename, `export_docx.py` now hashes the candidates and resolves the link only if every candidate is byte-identical. Different-content candidates remain non-clickable and generate the existing ambiguity warning.
- Adds byte-level duplicate-ID diagnostics to `asset-reference-audit-v7.json.xz`. Every duplicated local Asset ID is now classified as `identical`, `conflicting`, or `unreadable`, with per-path size and SHA-256 data plus structural kinds such as `dictation_mirror`, `image_mirror`, and `attachment_filename_variant`.
- The audit remains diagnostic and non-destructive. No asset is deleted, moved, renamed, or rewritten.


## v7 RC5

- Fixes literal filename rendering for missing attachments. Filenames containing Markdown-significant characters such as `[EXTERNE]` or `[Extern]` are now emitted through a safe code-span helper, so the DOCX shows the original filename without stray backslashes.
- The change is presentation-only: missing-asset detection, Asset IDs, audit counts, canonical JSON, and physical assets are unchanged.

## v7 RC4

- Makes missing visible attachments explicit in Markdown/DOCX. When a message references a local attachment by filename and Asset ID but no physical copy exists in the archive, the export now renders `⚠ Missing attachment: <filename>`, the Asset ID, and `Local archive status: missing` instead of an ambiguous archived-attachment block.
- Refines the audit classification of the 72 previously generic `tool_execution_attachment` image assets: all 72 are `container.open_image` execution outputs (`<<ImageDisplayed>>`) used for model-side image inspection. They are now classified as `internal_image_inspection` and deliberately remain unrendered in conversation exports.
- No asset deletion, relocation, or canonical JSON changes.

## v7 RC3

- Adds a clickable reference to the original `.m4a` next to each visible dictated user message when `metadata.dictation_asset_pointer` is available. The transcript remains the primary conversation text; the audio is linked, not embedded in the DOCX.
- Prefers the canonical `assets/dictation` copy when the same dictation asset ID also exists under another asset bucket. Duplicate physical copies are never deleted.
- Missing dictation audio is represented explicitly as unavailable and is counted by the existing unresolved-asset diagnostics.
- Extends `asset-reference-audit-v7.json.xz` with JSON provenance classification for local assets that remain unreferenced by DOCX/Markdown outputs. Categories include `dictation_source_active`, `dictation_source_inactive_or_hidden`, `inactive_branch_only`, `tool_execution_attachment`, `tool_source_or_internal`, `active_unrendered_reference`, `known_json_reference`, and `unexplained`.
- The audit remains strictly non-destructive. No asset is deleted, moved, filtered, or rewritten.
- RC3 deliberately does **not** render generic `tool / execution_output` attachments yet; they remain diagnostic until their UI visibility semantics are proven.

## v7 RC2

- Fixes DOCX conversion failures caused by XML-incompatible characters that can appear *after* Markdown parsing (for example through decoded entities). Token text, hyperlink labels/targets, image descriptions, captions, and titles are now sanitized again immediately before XML/DOCX insertion.
- Keeps the v7 generated-image export and cumulative asset-reference audit unchanged.
- The asset audit runs only after all requested DOCX conversions succeed, so a conversion error is reported first rather than producing a misleading partial audit.

This changelog documents the lineage of the current `gpt-exporter` architecture. Early prototypes before v2 were not consistently tagged and are intentionally summarized rather than reconstructed as formal releases.

## v7 — Generated-image recovery and asset-reference audit — 2026-08-17

**Status: FROZEN / current reference baseline.**

### Added

- Visible generated images carried by ChatGPT `tool / multimodal_text / image_asset_pointer` nodes are now exported instead of being discarded by the user/assistant role filter.
- Hidden technical duplicates marked `is_visually_hidden_from_conversation = true` remain excluded.
- A generated-image tool result is presented as ChatGPT output; when it directly follows an already-visible assistant answer in the same turn, the image is merged into that answer rather than creating a redundant heading.
- New cumulative `audit_asset_references.py` integrity check. It scans the physical `assets` corpus and verifies that every local asset ID appears through an explicit `Asset ID:` provenance marker in at least one generated root-level DOCX or persistent Markdown file.
- The audit also reports the inverse inconsistency: an output references an asset ID for which no local physical asset exists.
- Physical files below `assets` that do not expose a recognizable `file_...`, `file-...`, or `external_...` join key are reported separately instead of being silently ignored.
- Audit results are written to `reports\asset-reference-audit-v7.json.xz`. Discrepancies are warnings by default; `audit_asset_references.py --strict` returns exit code 2 when discrepancies exist.
- `export_all.py` automatically runs the cumulative audit after a successful DOCX or persistent-Markdown export. An operational audit failure is fatal, but ordinary discrepancy warnings are not.

### Validation performed before packaging

- `py_compile` succeeds for every Python source file.
- The real `Haken audio et tri-octave` `.json.xz` was used as the regression conversation.
- Its two visible generated-image tool nodes are now detected; the hidden duplicate of the second generated image remains excluded.
- Synthetic local PNG stand-ins using the two real `file_id` values were both embedded into the reconstructed DOCX, producing two drawing occurrences.
- The first generated image was merged into the preceding assistant answer; the second became a standalone ChatGPT image response because it follows a user message directly.
- With the STL attachment plus the two generated images present locally, the v7 audit found 3 unique local asset IDs, 3 rendered asset IDs, zero unreferenced local assets, and zero output references missing locally.

### Preservation policy

- Browser collection, asset caching, cumulative `.json.xz` storage, and broad over-collection are unchanged from v6.
- The new audit is diagnostic only: it never deletes, moves, filters, or rewrites an asset.
- Existing DOCX files are not silently rebuilt on installation. Run `py archive_chats.py --convert-only` once after upgrading to v7 to rebuild historical DOCX files with the new generated-image handling and obtain a meaningful whole-archive audit.

## v6 — Frozen reference release — 2026-08-17

**Status: FROZEN / previous reference baseline.**

### Added

- Visible DOCX provenance for archived assets without embedding every attachment.
- Embedded images receive a separate provenance block containing:
  - `Asset ID: file_...`
  - `Archive path: assets/...`
- Files present in visible-message `metadata.attachments` but not already represented by an inline asset pointer are listed at the correct message location.
- Archived attachment names in DOCX are clickable local hyperlinks when a physical local asset is known.
- Legacy `sandbox:/mnt/data/...` links are resolved to archived assets when the basename match is unique.
- Missing or ambiguous sandbox targets are retained as visible **non-clickable text** rather than being converted to dead or guessed links.

### Fixed

- Atlantis Word Processor compatibility for local links:
  - use `.\assets\...`;
  - use Windows backslashes;
  - keep literal spaces instead of `%20` URI encoding.
- Image provenance is emitted as its own paragraph, so text following an inline image in the same ChatGPT message no longer gets appended to the provenance line.
- Local links no longer depend on the temporary Markdown directory that is deleted after conversion.

### Preserved by design

- `collect_chatgpt_archive.js` is unchanged from the v4 collector baseline.
- Broad asset collection remains enabled; v6 does **not** narrow candidate detection.
- No asset is deleted, filtered, moved, or rewritten by the DOCX-provenance feature.
- `.json.xz + assets` remains the canonical source; DOCX is derived.

### Validation record

The frozen release was validated by a complete `--convert-only` rebuild of the local archive:

- 80 conversation DOCX exports completed;
- final status: `Archive completed successfully`;
- temporary Markdown directory removed after success;
- no `Unable to embed image` events;
- image format/DPI problems continued to be handled by the existing in-memory Pillow fallback;
- structured local asset resolution reported no unresolved assets in the conversation summaries inspected during the run;
- Atlantis Word Processor was tested manually with four relative-link forms: forms using forward slashes failed, while Windows forms `assets\...` and `.\assets\...` succeeded; v6 deliberately uses the explicit `.\assets\...` form.

Accepted warnings remain diagnostic rather than fatal:

- old sandbox links whose files are not present in the archived asset corpus;
- sandbox basenames with multiple local matches, where v6 refuses to guess;
- XML 1.0-incompatible control characters removed only while generating DOCX;
- normal `python-docx` image-reader failures that are successfully recovered by in-memory Pillow normalization.

## v5 — DOCX asset references — intermediate release — 2026-08-17

### Added

- First implementation of visible `file_id` and archive-path provenance in DOCX.
- First implementation of visible non-embedded `metadata.attachments` references at the originating message.
- First attempt at relative local hyperlinks for archived attachments.

### Known issues discovered during validation

- Hyperlink targets were written in URI/Web style (`assets/attachment/...` and/or `%20`), which Atlantis Word Processor did not resolve correctly.
- When an inline image was followed by text in the same message, the new provenance line could absorb the following text instead of keeping it as a separate paragraph.

These issues were corrected in v6. v5 is not the frozen reference release.

## Experimental `structured-assets-v5` — rejected / not part of the release lineage

An experimental branch attempted to restrict browser asset downloads to references classified as structurally proven attachments/media and to ignore `file_...` values found only in arbitrary text/log/code.

The experiment was rejected before adoption because it conflicted with the archive's primary preservation policy. The local asset corpus intentionally contains much more than images embedded in DOCX, and a broad over-collecting policy is safer than a narrow policy that might omit useful historical files.

**Decision retained in v6:** keep the v4 broad collector unchanged; tolerate stale fetch errors and optimize only with caches, never by narrowing preservation coverage.

## v4 — Robust DOCX image embedding — 2026-08-17

### Added

- `export_docx.py` first tries direct `python-docx` image insertion.
- If direct insertion fails but Pillow can read the image, the image is converted to PNG **in memory** and insertion is retried.
- Original archived files remain byte-for-byte untouched.
- The fallback applies to normal Markdown images and images appearing inside tables.

### Fixed

- WebP images that `python-docx` could not recognize.
- Several unusual JPEG files rejected by `python-docx`.
- JPEG metadata/DPI cases producing `ZeroDivisionError` during native-size calculation.

### Validation

The test archive completed with no remaining image-embedding warnings. Remaining warnings were limited to XML-incompatible control-character sanitation required by DOCX/XML.

## v3 — Legacy asset recovery from the physical archive — 2026-08-17

### Problem discovered

Regenerating historical DOCX files exposed an architectural flaw: `export_markdown.py` treated `reports\asset-download-index-v2.json.xz` as the only `file_id -> local file` mapping. Older archived assets existed physically under `assets\` but predated the registry and therefore appeared falsely unavailable during rebuilds.

### Fixed

- Registry entries remain the preferred mapping source.
- `export_markdown.py` recursively scans the physical `assets\` tree as a fallback.
- Filenames beginning with `file_...__` / `file-...__` reconstruct missing `file_id -> Path` mappings.
- `.failed` markers and zero-byte files are not treated as usable assets.
- A broken registry path can be repaired from a valid physical match.
- Duplicate candidates are accepted automatically only when their bytes are identical; conflicting contents are not guessed.

### Validation

For the historical `Tatouage HP-15C` test conversation, the v3 regenerated DOCX contained the same internal ZIP members and identical member contents as the previously trusted DOCX. The overall DOCX SHA differed only because ZIP container timestamps/metadata differed.

This established the key architectural rule still used by v6:

> `asset-download-index-v2` is a derived cache/report, not the archive source of truth.

## v2 — Current cumulative XZ/DOCX-root archive architecture

v2 established the architecture on which v3-v6 are based.

### Archive layout

```text
%USERPROFILE%\Documents\ChatGPT Archive\
├── 2026-..._<conversation-id>.docx
├── downloads\
│   └── *.json.xz
├── assets\
└── reports\
```

### Major changes

- Conversation sources stored individually as XZ-compressed JSON.
- XZ files read directly with Python `lzma`; no temporary extraction step.
- Incoming/local comparison still uses the **uncompressed UTF-8 JSON byte size**.
- Cumulative semantics:
  - new conversation -> import;
  - larger incoming JSON -> replace local copy and regenerate export;
  - equal/smaller incoming JSON -> preserve larger/equal local copy;
  - conversation absent from current bundle -> keep local copy.
- Final DOCX files moved directly to the archive root.
- Markdown became a temporary intermediate format during normal DOCX creation.
- Temporary Markdown is deleted only after successful DOCX conversion and retained after failure for diagnosis.
- Optional persistent Markdown remains available explicitly.
- Legacy `exports\docx` / `exports\markdown` migration added, with transactional collision handling.
- Large machine-readable reports moved to XZ storage.
- Browser bundle remains a temporary transfer object and is deleted only after a successful complete run.

## Pre-v2 prototypes

Earlier versions established the initial browser/Python split and basic conversation/media export behavior. They are not treated as frozen releases because the durable archive model, XZ storage, root-level DOCX layout, and transactional migration semantics were standardized in v2.
