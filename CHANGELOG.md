# Changelog

## Unreleased — Multi-provider application shell

- Adds **Discord** as the second concrete conversation provider alongside ChatGPT.
- The top-level provider chooser now lists both **ChatGPT** and **Discord** while keeping ChatGPT selected by default.
- Adds a Discord native data-package adapter for the `Messages` section. Current Discord packages use JSON transcripts; older CSV transcripts are also accepted for compatibility.
- Normalizes one Discord channel transcript into one provider-neutral `CanonicalConversation`, including message IDs, timestamps, contents, attachment URLs, and available guild/channel metadata.
- Does not invent missing participants: Discord's native data package contains the requesting account's sent messages, so those messages are normalized as `role="user"`.
- Adds a first-stage Discord GUI that selects an extracted data package, scans channel transcripts, normalizes them through the provider contract, and displays conversation/message counts.
- Keeps the shared core provider-neutral: importing `gpt_exporter.application` does not eagerly load either concrete provider, and concrete provider imports remain at the application boundary.
- No ChatGPT archive format, raw JSON/XZ data, DOCX rendering, or existing ChatGPT workflow is changed by this addition.


## v2.8 — GUI-first archive workflow — 2026-08-23

- Makes `gpt_exporter_gui.py` the normal day-to-day entry point while keeping the command-line tools available for diagnostics and advanced use.
- Adds the **Archive** menu and guided **Archive New Conversations…** workflow.
- Copies `collect_chatgpt_archive.js` to the clipboard automatically when the guided workflow opens.
- Detects a newly downloaded `chatgpt-archive-source.json` automatically and ignores an already existing bundle to avoid accidental reprocessing.
- Launches the canonical `archive_chats.py` pipeline automatically after bundle detection without duplicating archive/index logic in the GUI.
- Streams archive progress without freezing Tkinter, then refreshes the Browser automatically after success.
- Persists every archive run under `reports/` as `archive-workflow-YYYY-MM-DD_HH-MM-SS.log` and maintains `archive-workflow-latest.log`.
- Adds **Archive → Show Last Archive Log**.
- Closes the progress/log window automatically only after both the archive process and Browser refresh succeed; failures remain visible for diagnosis.
- Preserves the v2.7 archive model: canonical data remains cumulative `downloads/*.json.xz + assets/*`; DOCX, Markdown, SQLite indexes, manifests, reports, and workflow logs remain derived/rebuildable.
- Preserves Browser-managed projects, categories, and tags during incremental indexing.
- Validated on Windows with GitHub Actions for Python 3.12 and 3.13 plus repeated real end-to-end GUI smoke tests, including automatic appearance of newly archived conversations, current DOCX output, persistent logs, and success-only auto-close behavior.
- Known v2.8 limitation: the integrated archive workflow intentionally targets the default `%USERPROFILE%\Documents\ChatGPT Archive` location and refuses to write through a Browser instance opened on a different SQLite database.

See `docs/RELEASE_NOTES_V2.8.md` for the complete release notes and validation record.


## v2.7 — FROZEN — 2026-08-17

- Freezes the RC6 code as the v2.7 reference release after a complete Windows rebuild of all 80 archived conversations: 80 converted, 0 skipped, 0 failed.
- Final cumulative audit on the target archive: 1,610 physical asset files, 1,530 unique local Asset IDs, 1,455 rendered Asset IDs, 120 local assets intentionally not rendered, 45 referenced-but-local-missing assets, 45 duplicate local Asset IDs, and 0 unidentified asset files.
- All 45 duplicate Asset IDs are byte-identical: 28 `attachment_filename_variant`, 9 `dictation_mirror`, 8 `image_mirror`, 0 content conflicts and 0 unreadable duplicates.
- Final unreferenced classification: 1 `dictation_source_inactive_or_hidden`, 13 `inactive_branch_only`, 72 `internal_image_inspection`, 34 `tool_source_or_internal`. No unexplained physical orphan remains.
- The remaining 12 non-identical same-basename historical sandbox-link occurrences were reviewed against canonical conversation JSON. Provenance cannot identify one exact local target without guessing, so they deliberately remain non-clickable.
- No canonical `.json.xz` format, asset layout, collection coverage, or deletion policy changed between RC6 and this frozen v2.7 package. The executable source code is byte-identical to RC6; only release documentation and source-hash manifests were finalized.



## v2.7 RC6

- Fixes a blind spot in the cumulative asset-reference audit: local assets reached through actual DOCX hyperlink relationships are now counted as rendered references even when the visible paragraph has no separate `Asset ID:` provenance line. This is especially important for historical `sandbox:/mnt/data/...` download links that `export_docx.py` successfully resolves to `assets\...`.
- Extends persistent-Markdown auditing in the same direction by counting local `assets/...` link targets in addition to explicit `Asset ID:` lines.
- Improves ambiguous historical sandbox-link recovery without guessing: when several archived files share the same basename, `export_docx.py` now hashes the candidates and resolves the link only if every candidate is byte-identical. Different-content candidates remain non-clickable and generate the existing ambiguity warning.
- Adds byte-level duplicate-ID diagnostics to `asset-reference-audit-v2.7.json.xz`. Every duplicated local Asset ID is now classified as `identical`, `conflicting`, or `unreadable`, with per-path size and SHA-256 data plus structural kinds such as `dictation_mirror`, `image_mirror`, and `attachment_filename_variant`.
- The audit remains diagnostic and non-destructive. No asset is deleted, moved, renamed, or rewritten.


## v2.7 RC5

- Fixes literal filename rendering for missing attachments. Filenames containing Markdown-significant characters such as `[EXTERNE]` or `[Extern]` are now emitted through a safe code-span helper, so the DOCX shows the original filename without stray backslashes.
- The change is presentation-only: missing-asset detection, Asset IDs, audit counts, canonical JSON, and physical assets are unchanged.

## v2.7 RC4

- Makes missing visible attachments explicit in Markdown/DOCX. When a message references a local attachment by filename and Asset ID but no physical copy exists in the archive, the export now renders `⚠ Missing attachment: <filename>`, the Asset ID, and `Local archive status: missing` instead of an ambiguous archived-attachment block.
- Refines the audit classification of the 72 previously generic `tool_execution_attachment` image assets: all 72 are `container.open_image` execution outputs (`<<ImageDisplayed>>`) used for model-side image inspection. They are now classified as `internal_image_inspection` and deliberately remain unrendered in conversation exports.
- No asset deletion, relocation, or canonical JSON changes.

## v2.7 RC3

- Adds a clickable reference to the original `.m4a` next to each visible dictated user message when `metadata.dictation_asset_pointer` is available. The transcript remains the primary conversation text; the audio is linked, not embedded in the DOCX.
- Prefers the canonical `assets/dictation` copy when the same dictation asset ID also exists under another asset bucket. Duplicate physical copies are never deleted.
- Missing dictation audio is represented explicitly as unavailable and is counted by the existing unresolved-asset diagnostics.
- Extends `asset-reference-audit-v2.7.json.xz` with JSON provenance classification for local assets that remain unreferenced by DOCX/Markdown outputs. Categories include `dictation_source_active`, `dictation_source_inactive_or_hidden`, `inactive_branch_only`, `tool_execution_attachment`, `tool_source_or_internal`, `active_unrendered_reference`, `known_json_reference`, and `unexplained`.
- The audit remains strictly non-destructive. No asset is deleted, moved, filtered, or rewritten.
- RC3 deliberately does **not** render generic `tool / execution_output` attachments yet; they remain diagnostic until their UI visibility semantics are proven.

## v2.7 RC2

- Fixes DOCX conversion failures caused by XML-incompatible characters that can appear *after* Markdown parsing (for example through decoded entities). Token text, hyperlink labels/targets, image descriptions, captions, and titles are now sanitized again immediately before XML/DOCX insertion.
- Keeps the v2.7 generated-image export and cumulative asset-reference audit unchanged.
- The asset audit runs only after all requested DOCX conversions succeed, so a conversion error is reported first rather than producing a misleading partial audit.

This changelog documents the lineage of the current `gpt-exporter` architecture. Early prototypes before v2 were not consistently tagged and are intentionally summarized rather than reconstructed as formal releases.

## v2.7 — Generated-image recovery and asset-reference audit — 2026-08-17

**Status: FROZEN / current reference baseline.**

### Added

- Visible generated images carried by ChatGPT `tool / multimodal_text / image_asset_pointer` nodes are now exported instead of being discarded by the user/assistant role filter.
- Hidden technical duplicates marked `is_visually_hidden_from_conversation = true` remain excluded.
- A generated-image tool result is presented as ChatGPT output; when it directly follows an already-visible assistant answer in the same turn, the image is merged into that answer rather than creating a redundant heading.
- New cumulative `audit_asset_references.py` integrity check. It scans the physical `assets` corpus and verifies that every local asset ID appears through an explicit `Asset ID:` provenance marker in at least one generated root-level DOCX or persistent Markdown file.
- The audit also reports the inverse inconsistency: an output references an asset ID for which no local physical asset exists.
