# Legacy DOCX import

Historical ChatGPT conversations may exist only as `.docx` files created by copying the full ChatGPT web page into Microsoft Word.  These files are valuable archive sources, but they are not equivalent to native ChatGPT JSON exports and must not be silently treated as such.

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

The date is intentionally day-granular.  Word core properties may retain a more precise creation timestamp; that timestamp is preserved separately and is not required in the filename.

Historical filename forms containing `HHMMSS` or a space-separated date are recognized by the audit scanner, but are reported as non-normalized.

## Phase 1: read-only audit

The first implementation is deliberately non-destructive.  It does **not**:

- modify source DOCX files;
- copy them into the canonical archive;
- synthesize canonical JSON/XZ;
- modify `conversations-index.sqlite`;
- assign User/Assistant roles beyond a conservative first-message hint.

It records:

- source path, size, and SHA-256;
- category/date/title filename hints;
- Word creation/modification timestamps;
- paragraph, table, and heading counts;
- preserved ChatGPT hyperlink sentinels;
- the first likely visible user message;
- possible structural boundary count;
- an explicit confidence level and notes.

Run a directory audit with:

```text
py scan_legacy_docx.py "D:\path\to\old conversations" --json legacy-docx-report.json --debug
```

The JSON report schema identifier is:

```text
gpt-exporter-legacy-docx-audit-v1
```

## Why turn reconstruction is conservative

The sampled historical files preserve useful Word structure, including paragraphs, headings, tables, hyperlinks, and blank separators.  However, the same structural gaps can also occur inside an Assistant response around rich content.  Therefore a blank-gap heuristic is suitable for audit candidates but not sufficient evidence to assign roles automatically.

The source DOCX is the evidence.  Derived parsing must remain reproducible and replaceable as the parser improves.

## Planned Phase 2

After the corpus-level audit is satisfactory:

1. define a versioned legacy conversation representation;
2. preserve each original DOCX unchanged with its SHA-256 provenance;
3. reconstruct User/Assistant turns only where confidence is adequate;
4. explicitly represent unresolved/missing attachment references when visible in the DOCX;
5. generate canonical derived JSON/XZ marked as `legacy_docx` provenance;
6. extend the index schema so modern ChatGPT exports and legacy DOCX imports share search and organization without pretending they have identical provenance;
7. add GUI import/preview workflow and reparse support.

No Phase 2 migration should weaken the existing non-destructive archive invariants.
