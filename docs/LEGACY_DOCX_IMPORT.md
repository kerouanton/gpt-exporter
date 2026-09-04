# Legacy DOCX import

Historical ChatGPT conversations may exist only as `.docx` files created by copying the full ChatGPT web page into Microsoft Word. These files are valuable archive sources, but they are not equivalent to native ChatGPT JSON exports and must not be silently treated as such.

For native conversations, the durable source remains the exported JSON/XZ and DOCX is a derived presentation format. For legacy conversations, the historical DOCX is the immutable source of evidence and all JSON/SQLite representations are derived from it.

## Preferred filename convention

Use:

```text
<CATEGORY> GPT <YYYY-MM-DD> <TITLE>.docx
```

Examples:

```text
PKI GPT 2026-04-03 Installation PiOS sur RPi.docx
HAM GPT 2026-04-03 BOM transverter 3.2-20 GHz.docx
IT GPT 2026-03-27 Problème envoi email Gandi.docx
```

The filename supplies category/date/title hints. The source DOCX SHA-256 is the durable identity used by the legacy importer.

## Provenance and safety invariants

Legacy import is deliberately non-destructive:

- source DOCX files are never modified;
- SHA-256 is verified before SQLite import;
- role inference is stored separately from raw Word evidence;
- ambiguous regions remain `unknown` instead of being silently forced to User/Assistant;
- SQLite conversation IDs are stable and derived from source SHA-256;
- legacy conversations are visibly marked as `Legacy DOCX` in the browser;
- filename category hints (`HAM`, `PKI`, `IT`, `EMBEDDED`, etc.) are assigned as normal archive categories;
- import is idempotent and supports forced reindex without creating duplicates;
- the GUI/CLI validation pass does not modify SQLite;
- an SQLite backup is created before applied GUI/CLI imports;
- normalized legacy DOCX files are written to a separate output directory and never replace historical sources.

## Current validated corpus

The first real corpus contains 42 normalized DOCX files. The validated reconstruction currently yields:

```text
User turns:      304
Assistant turns: 311
Unknown turns:    39
Total turns:     654
```

All 42 source hashes validate, all 654 turns are present in `messages`, and all 654 are present in FTS5. A live browser search has been verified against legacy-only text.

## Pipeline

### 1. Audit source DOCX

```text
py scan_legacy_docx.py "F:\GPT" --json legacy-docx-report.json --debug
```

This inventories filename metadata, Word timestamps and structural evidence without changing the sources.

### 2. Build loss-minimizing Word IR

```text
py build_legacy_docx_ir.py "F:\GPT" --output legacy-docx-ir-v2.json
```

The v2 IR preserves ordered blocks plus Word evidence such as blank-block counts, alignment, indentation, shading, borders, numbering, run counts, bold/italic runs and hyperlinks.

### 3. Profile formatting signatures

```text
py profile_legacy_docx_ir.py legacy-docx-ir-v2.json --output legacy-docx-profile.json
```

The profile is used to validate corpus-level formatting signals without assigning roles by guesswork.

### 4. Infer roles conservatively

```text
py classify_legacy_docx_ir.py legacy-docx-ir-v2.json ^
  --output legacy-docx-ir-classified-v3.json ^
  --summary legacy-docx-role-summary-v3.json
```

PowerShell form:

```powershell
py classify_legacy_docx_ir.py legacy-docx-ir-v2.json `
  --output legacy-docx-ir-classified-v3.json `
  --summary legacy-docx-role-summary-v3.json
```

Current inference version: `legacy-role-inference-v3`.

Strong Word-format anchors are preferred. Assistant-tail phrases such as proposed next steps are explicitly guarded against as false User turns. Ambiguous regions remain `unknown`.

### 5. Build normalized turns

```powershell
py build_legacy_docx_turns.py legacy-docx-ir-classified-v3.json `
  --output legacy-docx-turns.json
```

The turn representation preserves:

- role and confidence;
- normalized searchable content;
- source block count;
- first/last Word order;
- exact source order references;
- contributing block kinds.

### 6. Validate SQLite import (dry-run)

```powershell
py import_legacy_docx_turns.py legacy-docx-turns.json `
  --docx-root "F:\GPT"
```

Expected validated corpus result:

```text
Validated conversations: 42
Validated turns: 654
Validation failures: 0
Dry-run only: SQLite was not modified.
```

### 7. Apply SQLite/FTS5 import

```powershell
py import_legacy_docx_turns.py legacy-docx-turns.json `
  --docx-root "F:\GPT" `
  --apply
```

Use `--force` when a newer importer needs to refresh metadata such as origin/category display without changing stable conversation IDs.

### 8. Verify the resulting index

```text
py verify_legacy_index.py --query "grands rangements"
```

The verifier reports legacy conversation count, turn count in `messages`, turn count in FTS5, and legacy FTS matches for the supplied query.

### 9. Browse and search

```text
py archive_browser.py
```

Legacy conversations appear with:

```text
Origin: Legacy DOCX
```

and use their filename category hint through the normal Category mechanism.

### 10. GUI import of an already reconstructed corpus

```text
py legacy_import_gui.py
```

The GUI intentionally starts from `legacy-docx-turns.json`, not raw DOCX. It provides:

- turns JSON selection;
- source DOCX directory selection;
- target SQLite selection;
- read-only validation first;
- explicit confirmation before Apply;
- consistent SQLite backup using SQLite's backup API;
- import result summary.

This keeps the validated reconstruction pipeline separate from the database write step.

### 11. Generate normalized legacy DOCX derivatives

```powershell
py build_legacy_canonical_docx.py legacy-docx-turns.json `
  --output-dir legacy-normalized-docx
```

For an initial visual smoke test, generate only one document:

```powershell
py build_legacy_canonical_docx.py legacy-docx-turns.json `
  --output-dir legacy-normalized-docx `
  --limit 1
```

Current renderer version: `legacy-canonical-docx-v1`.

Each derived DOCX contains:

- the normalized conversation title;
- an explicit `Legacy DOCX normalized derivative` warning;
- source filename and SHA-256;
- parser / role-inference / turn-builder / renderer versions;
- category/date hints;
- one section per reconstructed User, Assistant or Unknown turn;
- reconstruction confidence/source-order metadata when available;
- an explicit warning when one or more turns remain `UNKNOWN`.

Derived filenames end in:

```text
[normalized].docx
```

so they cannot silently overwrite the historical source filename. Existing normalized derivatives are kept unless `--overwrite` is supplied.

## Rebuilding the complete archive

The historical index `rebuild` command only knows how to rebuild native JSON/XZ conversations. Use the legacy-aware wrapper instead when legacy conversations must be retained:

```text
py rebuild_archive_with_legacy.py --help
```

The wrapper reconstructs the native index and then reimports the normalized legacy turns, with backup/validation safety.

## Storage model

Native path:

```text
ChatGPT JSON/XZ -> generated DOCX -> SQLite/FTS5
```

Legacy path:

```text
immutable historical DOCX
        -> Word IR v2
        -> conservative role inference v3
        -> normalized turns v1
        -> SQLite/FTS5 + provenance
        -> optional normalized DOCX derivative
```

The legacy DOCX remains the authoritative source. Derived IR/turn JSON and normalized DOCX files may be regenerated when parser or inference logic improves.

## Known limitations

- attachments that were not embedded/preserved in the copied Word page cannot be recovered automatically;
- 39 current turn regions remain deliberately `unknown` in the validated corpus;
- some captures begin in the middle of an Assistant response;
- the legacy parser reconstructs searchable conversation structure, not the exact original ChatGPT DOM;
- role inference is corpus-informed and versioned, so future parser versions may improve the reconstruction while preserving the original source and provenance.
