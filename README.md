# ChatGPT Archiver

> **Current code package: v2.7 — frozen release — 2026-08-17**  
> **Previous frozen baseline: v2.6.** v2.7 was validated on the complete 80-conversation local corpus. It preserves the canonical archive format, restores visible generated-image tool results, links original dictation audio, makes missing visible attachments explicit, and adds a cumulative asset-reference audit.

## Frozen-release invariants

The following rules are inherited from the v2.6 frozen design and remain invariants in v2.7:

1. **Canonical archive data is `downloads\*.json.xz + assets\*`.** DOCX, Markdown, manifests, indexes, and reports are derived and rebuildable.
2. **The archive is cumulative.** A normal run never removes an older conversation or an existing asset because it is absent from the current browser bundle.
3. **Asset collection remains deliberately broad.** The JavaScript collector may over-collect candidates or encounter stale 404/403 responses; this is preferable to narrowing collection and accidentally missing recoverable assets.
4. **Existing assets are never pruned during normal operation.** Browser cache and Python reports are optimizations/diagnostics, not authorities for deleting files.
5. **The `file_id` embedded in archived filenames is the stable join key** between conversation JSON references and physical files under `assets\`.
6. **DOCX is a readable representation, not the source of truth.** Images may be embedded; non-image attachments are referenced rather than embedded.
7. **Visible DOCX asset references must remain locally usable.** Local hyperlinks use Windows-relative targets such as `.\assets\attachment\...` with literal spaces, verified with Atlantis Word Processor.
8. **Legacy sandbox links are resolved conservatively.** A unique archived basename match becomes a local link; missing or ambiguous matches remain visible but non-clickable. No guessed target is created.
9. **Markdown remains temporary during normal DOCX generation.** Persistent Markdown is produced only when explicitly requested.
10. **Source assets are never rewritten for DOCX compatibility.** Unsupported raster images are normalized to PNG in memory only for embedding.

See `CHANGELOG.md` for the release history and `FROZEN_VERSION.md` / `SOURCE_SHA256SUMS.txt` for exact release identification. These documentation files describe the frozen package; they do not modify its source code.

This tool archives the non-archived conversations currently shown at the root of the ChatGPT sidebar and creates one DOCX file per conversation. Markdown is used only as a temporary intermediate format during normal DOCX generation.

Conversations stored inside a **Project** are not included by this version.

## Archive model

The local archive is cumulative.

A browser export represents the conversations currently visible on ChatGPT. It does not replace the local archive and does not authorize deletion of older local conversations.

For each conversation ID:

- a new conversation is imported and exported;
- a larger incoming conversation JSON replaces the local copy and regenerates its DOCX;
- an incoming JSON of equal or smaller UTF-8 byte size is ignored, preserving the larger local version;
- a conversation absent from the current browser export remains preserved locally;
- existing assets are never deleted during a normal run.

The normal command is therefore:

```text
py archive_chats.py
```

Do not use `--fresh` for routine archiving.

## Principle

No cookie, cURL command, or manually saved conversation list is required.

The browser collector runs inside an already authenticated ChatGPT tab. It reads the current session automatically and creates one private file:

```text
chatgpt-archive-source.json
```

This file contains complete conversation JSON data, internal ChatGPT assets encoded in Base64, and URL metadata for external image carousels. Keep it private.

The browser bundle is a temporary transfer file. Python reads it directly from the Windows Downloads directory. It is not copied into the project and is deleted only after the complete archive run succeeds. If the run fails, the source JSON is left in place for retry or diagnosis.

## 1. Install the Python dependencies

Run once:

```text
py -m pip install -r requirements.txt
```

Optional environment check:

```text
py check_environment.py
```

The environment check validates the active pipeline, creates missing working directories, and reports whether a current browser bundle is available. The browser bundle is not required for the check itself. If it is missing, the console displays the complete browser procedure needed to generate it.

## 2. Generate the browser bundle

1. Open `https://chatgpt.com/` and make sure you are logged in to the correct account.
2. Open Firefox Developer Tools with `F12`.
3. Select **Console**.
4. Open `collect_chatgpt_archive.js` in a text editor.
5. Copy the complete script, paste it into the Console, and press Enter.
6. Wait until the browser downloads:

```text
chatgpt-archive-source.json
```

The console first displays the collector version, the number and titles of the conversations found, then the retrieval of each complete conversation. Internal ChatGPT asset IDs are checked against a small per-account browser cache before any download request is sent.

The asset cache is stored in Firefox `localStorage` for the current ChatGPT account. It is only an optimization cache; the persistent archive and Python reports remain authoritative.

Cache policy:

```text
downloaded              -> skip future browser downloads
HTTP 404                -> skip for 30 days, then retry
descriptor with no URL  -> skip for 30 days, then retry
HTTP 403                -> retry on the next run
other errors            -> retry on the next run
new file_id              -> download normally
```

The first run with this collector version populates the browser cache and can therefore still perform many asset requests. Later runs with the same Firefox profile and ChatGPT account should issue only requests for new assets and retryable failures.

If you are upgrading from an older gpt-exporter version and already have
`reports\asset-download-index-v2.json.xz` (or the legacy uncompressed `.json`), you can seed Firefox once from that existing report before running the new collector:

```text
py build_browser_asset_cache_seed.py
```

This creates:

```text
%USERPROFILE%\Documents\ChatGPT Archive\reports\browser-asset-cache-seed.js
```

Paste that generated seed script once into the ChatGPT Firefox Console, wait for the confirmation message, then run `collect_chatgpt_archive.js` normally. The seed script contains only asset-state data derived from your local report and can be deleted afterwards. This avoids repeating a full asset scan just to initialize the new browser cache.

For diagnostics, the console exposes:

```text
gptExporterAssetCache.stats()
gptExporterAssetCache.forget("file_id_here")
gptExporterAssetCache.clear()
```

Clearing this browser cache does not delete any archived data. It only causes the collector to rediscover asset state on a later run.

External carousel images are only queued in the browser. Python downloads them later, outside the browser Content Security Policy.

Firefox may display a self-XSS warning before allowing pasted console code. Follow Firefox's on-screen instruction only after verifying that the pasted code is the local `collect_chatgpt_archive.js` supplied with this project.

The collector obtains the temporary access token and account ID from `/api/auth/session`; it does not write either value into the downloaded archive file.

## 3. Run the cumulative archive

Leave the newly downloaded file in the normal Windows Downloads directory, then run:

```text
py archive_chats.py
```

The program reads `chatgpt-archive-source.json` directly from the Windows Downloads directory. It never copies or moves the file into the Python project. After all import, inventory, manifest, temporary Markdown, and DOCX steps complete successfully, the consumed source JSON is deleted from Downloads. On failure it is preserved.

The importer then compares the current bundle with the cumulative local archive. Only new or larger conversations are exported during that run.

`reports\asset-download-index-v2.json.xz` is maintained as a cumulative asset registry. It preserves known successful and failed asset states across runs. When the browser reports a cached successful asset, Python verifies that the corresponding local file still exists before reusing it. Previously downloaded external carousel images are also reused instead of being downloaded again.

For export, the registry is intentionally **not treated as the only source of truth for legacy files**. `export_markdown.py` also scans the persistent `assets\` tree and reconstructs missing `file_id -> local file` mappings from filenames such as `file_...__image.png`. This is required for assets archived before the current cumulative registry was introduced. Registry entries remain preferred; the disk scan is a fallback and never overwrites a valid registry path. Duplicate local files are accepted automatically only when their contents are byte-identical.

Persistent archive data is stored outside the Python project under:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
├── 2026-..._<conversation-id>.docx
├── downloads\
├── assets\
└── reports\
```

The final DOCX files are therefore written directly to:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
```

During a normal export, Markdown is generated in a temporary directory under the Windows temporary-file location. The temporary Markdown directory is deleted after the DOCX batch succeeds. If DOCX conversion fails, that temporary directory is preserved and its path is printed for diagnosis.

DOCX image embedding first uses the original archived file directly. If `python-docx` does not recognize an otherwise readable raster image (notably WebP and some unusual JPEG files), `export_docx.py` uses Pillow to normalize that image to PNG **in memory** and retries the insertion. The original file under `assets\` is never modified. Supported images that `python-docx` already accepts remain embedded directly without re-encoding.

DOCX exports also preserve visible asset provenance. Images that are embedded in the document receive a separate provenance paragraph containing their ChatGPT `file_id` and archive-relative `assets/...` path, so text that follows an image in the same ChatGPT message remains a distinct paragraph. Files attached to a visible message through `metadata.attachments` but not already represented by an inline asset pointer are listed at that message location instead of being embedded. The reference includes the original display name, `file_id`, and archive-relative path. Local attachment hyperlinks in the DOCX are rewritten relative to the final DOCX location using Windows-style targets such as `.\assets\attachment\...`, with literal spaces rather than `%20`; this is compatible with Atlantis Word Processor and avoids any dependency on the temporary Markdown directory.

Legacy `sandbox:/mnt/data/...` links generated by ChatGPT are handled conservatively during DOCX conversion. If the referenced basename uniquely matches a file already preserved below the archive `assets\` tree, the DOCX hyperlink is rewritten to that archived file. If no unique archived match exists, the visible link label is kept as ordinary non-clickable text instead of creating a dead hyperlink to a temporary sandbox path.

This provenance layer does **not** change browser collection policy and does not delete, filter, or move archived assets. The broad JavaScript collector remains unchanged. It also does not claim that every file below `assets\` must appear in a DOCX: assets referenced only in hidden/tool/inactive graph nodes or merely mentioned as text remain preserved in the canonical JSON/XZ plus `assets\` archive even when they are not part of the visible DOCX conversation.

On the first normal run after upgrading from an older version, `archive_chats.py` automatically moves legacy `downloads`, `assets`, `exports`, and `reports` directories out of the project and into this Documents archive root, provided the matching destination directories do not already exist. It then migrates existing `exports\docx\*.docx` files to the archive root and removes the legacy `exports\markdown\` directory. A conflicting DOCX with different contents stops migration before output files are moved or deleted.

## Subsequent archives

For every later archive:

1. Run `collect_chatgpt_archive.js` again in the ChatGPT Console.
2. Leave the downloaded `chatgpt-archive-source.json` in Windows Downloads.
3. Run:

```text
py archive_chats.py
```

The new browser bundle is processed directly in Downloads and deleted after a successful run, leaving the filename available for the next browser export.

Deleting conversations from ChatGPT does not delete their existing local JSON, assets, or DOCX files.

The browser asset cache is intentionally independent from the local archive. If Firefox profile data is cleared, the next collector run may perform a full asset scan again, but the Python importer still preserves existing local assets and the cumulative asset registry.

## Compressed local JSON storage

Conversation source files kept in the cumulative archive are stored individually as XZ-compressed JSON:

```text
%USERPROFILE%\Documents\ChatGPT Archive\downloads\*.json.xz
```

Python reads them directly through the standard-library `lzma` module; no temporary extraction file is created. The cumulative comparison still uses the **uncompressed UTF-8 JSON byte size**, so the existing rule (keep the largest known conversation version) is unchanged.

On the first run after upgrading, existing `downloads\*.json` files are migrated transactionally: a `.json.xz.tmp` file is written, decompressed and compared byte-for-byte with the source, renamed to `.json.xz`, and only then is the original `.json` removed.

Large machine-readable report JSON files are also stored as XZ:

```text
reports\asset-download-index-v2.json.xz
reports\asset-manifest.json.xz
reports\inventory-media-report.json.xz
```

Small control files and human-readable diagnostics remain uncompressed, including `current-batch.json`, `.txt` reports, and `browser-asset-cache-seed.js`.

## Current batch

During a normal run, `import_browser_bundle.py` writes:

```text
%USERPROFILE%\Documents\ChatGPT Archive\reports\current-batch.json
```

This file lists only conversations that were newly imported or replaced by a larger version during the current run. `export_all.py` restricts DOCX generation to this batch; Markdown is only an intermediate representation during that conversion.

When the batch is empty, `archive_chats.py` reports that there are no new or larger conversations and leaves the existing archive untouched.

## Other modes

### Rebuild every export from local JSON files

```text
py archive_chats.py --convert-only
```

This skips browser-bundle import and rebuilds all root-level DOCX files from the conversation `.json.xz` files already present in `downloads`.

Because this mode intentionally processes all local conversation JSON files, use it only when a complete rebuild is desired.

### Generate persistent Markdown explicitly

Normal archive runs do not retain Markdown. If Markdown is needed later for a website or another workflow, generate it explicitly with:

```text
py export_all.py --markdown-only --overwrite-all
```

Those files are kept in:

```text
%USERPROFILE%\Documents\ChatGPT Archive\markdown\
```

A later normal archive run does not delete this explicitly generated directory.

### Skip media inventory

```text
py archive_chats.py --skip-assets
```

This skips media inventory and asset-manifest generation during the run. Existing local assets are preserved.

### Destructive reset

```text
py archive_chats.py --fresh
```

**Warning:** this option deletes the complete generated local archive before importing the current browser bundle, including:

```text
downloads\
assets\
reports\
markdown\        (if explicitly generated)
*.docx             (at the ChatGPT Archive root)
legacy exports\  (if still present)
```

These paths are below `%USERPROFILE%\Documents\ChatGPT Archive\`, not inside the Python project.

Use `--fresh` only when deliberately starting a completely new archive from the current browser bundle. It is not part of the normal cumulative workflow.

## Main files

| File | Purpose |
|---|---|
| `collect_chatgpt_archive.js` | Collects root-level conversations and browser-accessible assets |
| `build_browser_asset_cache_seed.py` | Creates an optional one-time Firefox cache seed from the existing cumulative asset report |
| `archive_chats.py` | Main Python entry point and cumulative workflow coordinator |
| `import_browser_bundle.py` | Imports the browser bundle, preserves larger local conversations, maintains the cumulative asset registry, reuses local assets, and writes the current batch |
| `inventory_media.py` | Inventories media references found in the local conversation `.json.xz` files |
| `build_asset_manifest.py` | Builds a cumulative diagnostic manifest of media and attachment references found in local conversation JSON/XZ files |
| `export_all.py` | Generates root-level DOCX files for all local conversation `.json.xz` files or for a specified batch, using temporary Markdown by default, then runs the cumulative asset-reference audit |
| `audit_asset_references.py` | Verifies that physical local asset IDs are represented by explicit provenance markers or real local-asset hyperlinks in generated DOCX/persistent Markdown; hashes duplicate IDs and writes `reports\asset-reference-audit-v2.7.json.xz` |
| `export_markdown.py` | Converts one conversation `.json.xz` file to Markdown, resolves assets from the registry plus a safe local-disk fallback scan, exports visible generated-image tool results, and emits visible `file_id`/archive-path provenance for inline assets and message attachments; direct/manual use defaults to `ChatGPT Archive\markdown` |
| `export_docx.py` | Converts Markdown to DOCX, embedding supported images directly, normalizing unsupported raster formats through Pillow only when needed, rewriting local hyperlinks as Atlantis-compatible Windows-relative targets, and resolving archived `sandbox:/mnt/data/...` links when possible; direct/manual output defaults to the `ChatGPT Archive` root |
| `check_environment.py` | Validates the active pipeline and Python dependencies |

The following files are legacy standalone tools and are not called by `archive_chats.py`:

```text
download_conversations.py
download_assets.py
```

They may be retained for historical or manual use, or moved to a separate `legacy` directory.

## External image carousels

The collector explicitly detects ChatGPT image carousels stored in:

```text
metadata.content_references[]
type: image_v2
images[].content_url
images[].thumbnail_url
images[].original_content_url
```

The JavaScript does not download those remote images because ChatGPT's browser Content Security Policy blocks cross-site `fetch()` requests. Instead, it records all candidate URLs and associates each image with the originating message.

During a normal run:

```text
py archive_chats.py
```

`import_browser_bundle.py` downloads external images directly from Python, trying the candidate URLs recorded by the collector.

Downloaded images are stored below:

```text
%USERPROFILE%\Documents\ChatGPT Archive\assets\attachment\
```

They are inserted into Markdown and DOCX near the associated ChatGPT message. A remote host may reject or remove an image; this is reported as a warning without aborting the remaining archive.

At startup, the browser console must display:

```text
Collector version: asset-cache-v1
```

## Placement of external image carousels

External `image_v2` results are anchored to the internal image marker stored in the ChatGPT message text. They are emitted before the surrounding answer text when ChatGPT originally displayed the carousel there.

If an older export contains image metadata without a marker, the images are appended to that message as a fallback.

## Privacy and backup

The following paths may contain complete private conversations, uploaded files, generated documents, or remote image copies:

```text
%USERPROFILE%\Downloads\chatgpt-archive-source.json   (temporary)
%USERPROFILE%\Documents\ChatGPT Archive\
```

Keep them private and include them in the backup strategy for the cumulative archive.

## Generated images and v2.7 asset-reference audit

ChatGPT-generated images can be stored in the conversation graph as visible tool results rather than ordinary assistant messages:

```text
author.role = tool
content.content_type = multimodal_text
parts[].content_type = image_asset_pointer
```

v2.7 exports those visible image results as ChatGPT content while continuing to ignore tool nodes marked `is_visually_hidden_from_conversation = true` and unrelated technical tool output. The physical image is resolved through the existing asset registry plus local `assets` fallback scan; no collector change is required.

After every successful export batch, `export_all.py` runs:

```text
audit_asset_references.py
```

The audit compares the physical local asset corpus with both explicit `Asset ID:` provenance markers and real local-asset hyperlink targets found in all root-level DOCX files and any persistent files below `ChatGPT Archive\markdown`. It reports:

```text
local asset present + output provenance present   -> OK
local asset present + no output provenance        -> WARNING
output provenance present + no local asset        -> WARNING
physical asset file has no recognizable ID          -> WARNING
```

The complete machine-readable result is stored in:

```text
%USERPROFILE%\Documents\ChatGPT Archive\reports\asset-reference-audit-v2.7.json.xz
```

Warnings are deliberately non-destructive and non-fatal. Broad collection can retain technical or historical assets that are not visible in the active conversation branch, so an unreferenced asset is a signal for review, not proof of corruption. The audit never removes anything.

### Original dictation audio (RC3+)

When a visible user message contains `metadata.dictation_asset_pointer`, the transcript is exported normally and an additional provenance block is appended at the same message position:

```text
🎙 Original dictation audio: Listen (.m4a)
Asset ID: file_...
Archive path: assets/dictation/file_...m4a
```

The DOCX hyperlink is relative to the archive root, so the audio remains playable as long as the `ChatGPT Archive` tree is kept together. The `.m4a` is linked rather than embedded. If duplicate copies exist, the canonical `assets/dictation` copy is preferred; no duplicate is removed.

RC3 also enriches the asset-audit report with JSON provenance categories for unreferenced local assets. RC4 refines this after corpus-wide inspection: image attachments produced by `container.open_image` as `tool / execution_output` with `<<ImageDisplayed>>` are classified as `internal_image_inspection`, because they are model-side inspection artifacts rather than conversation content. They remain archived but are deliberately not rendered. Other tool/internal sources remain diagnostic only.


### DOCX hyperlink references and duplicate-ID integrity

The cumulative audit now treats a DOCX hyperlink relationship whose target points into `assets\...` as a real rendered asset reference. This closes the gap where an old `sandbox:/mnt/data/...` download link had been successfully converted into a local clickable DOCX link but the audit still reported its Asset ID as unreferenced because no separate visible `Asset ID:` line existed.

For historical sandbox links with several same-name local candidates, the DOCX exporter compares candidate bytes. It resolves the link only when all candidates are SHA-256-identical; if their bytes differ, the link remains deliberately non-clickable rather than guessing.

The final corpus validation left 12 such non-identical same-basename sandbox-link occurrences. They were inspected against their canonical conversation JSON. Six are generic or generated `README.md` links for which the canonical JSON contains no reliable sandbox-path-to-file-ID mapping; the other six are network-rescue script links for which the same conversation contains two or three distinct uploaded revisions with the same basename. Because provenance does not identify one exact physical candidate, those 12 links intentionally remain visible but non-clickable. This is a preservation decision, not an exporter failure.

Duplicate local Asset IDs are also hashed during the audit. The report records `content_status` (`identical`, `conflicting`, or `unreadable`), file sizes and SHA-256 values for every duplicate path. This is diagnostic only and never removes duplicate physical copies.

### Missing visible attachments

If a visible message references a local attachment that is no longer present under `assets`, the export preserves the fact that the attachment existed and names it explicitly:

```text
⚠ Missing attachment: example.pdf
Asset ID: file_...
Local archive status: missing
```

This is intentionally a rendering/audit feature only. It never deletes, substitutes, or fabricates the missing file.

v2.7 preserves Markdown-significant characters in the original filename literally when producing DOCX output; for example `[EXTERNE]` remains `[EXTERNE]` rather than acquiring visible escape backslashes.

After upgrading from v2.6, rebuild all derived DOCX files once so historical generated images can be recovered and the cumulative audit compares against current outputs:

```text
py archive_chats.py --convert-only
```
