# Legacy DOCX import

Historical ChatGPT conversations may exist only as `.docx` files created by copying the full ChatGPT web page into Microsoft Word. These files are valuable archive sources, but they are not equivalent to native ChatGPT JSON exports and must not be silently treated as such.

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

The date is intentionally day-granular. Word core properties may retain a more precise creation timestamp; that timestamp is preserved separately and is not required in the filename.

Historical filename forms containing `HHMMSS` or a space-separated date are recognized by the audit scanner, but are reported as non-normalized.

## Phase 1: read-only audit

The first implementation is deliberately non-destructive. It does **not**:

- modify source DOCX files;
- copy them into the canonical archive;
- synthesize canonical JSON/XZ;
- modify `conversations-index.sqlite`;
- assign User/Assistant roles from weak layout heuristics.

It records source provenance, filename hints, Word timestamps, structural counts, preserved ChatGPT sentinels, visible-text hints, and possible structural boundaries.

Run a directory audit with:

```text
py scan_legacy_docx.py "F:\GPT" --json legacy-docx-report.json --debug
```

The JSON report schema identifier is:

```text
gpt-exporter-legacy-docx-audit-v1
```

## Corpus findings

The first real corpus contained 42 normalized DOCX files. It confirmed that Word structure is rich enough to preserve useful evidence, but also showed that some captures begin in the middle of an Assistant response and that blank-gap counts do not reliably equal conversation-turn counts.

See `LEGACY_DOCX_CORPUS_FINDINGS.md` for the corpus-level observations.

## Phase 2: versioned intermediate representation

Phase 2 introduces a loss-minimizing intermediate representation without touching the canonical archive or SQLite index.

Each source becomes a `gpt-exporter-legacy-conversation-v1` object containing:

- immutable source path and SHA-256 provenance;
- filename category/date/title hints;
- Word creation/modification timestamps;
- parser version;
- `starts_mid_conversation = true/false/unknown` plus confidence;
- ordered Word blocks;
- block kinds such as `paragraph`, `heading`, `table`, and `hyperlink_sentinel`;
- role fields initialized to `unknown` unless stronger evidence is introduced later.

Build the aggregate intermediate representation with:

```text
py build_legacy_docx_ir.py "F:\GPT" --output legacy-docx-ir.json
```

This command is also non-destructive: it reads the legacy DOCX files and writes only the requested JSON output.

The intermediate representation is intentionally not a synthetic native ChatGPT export. It remains explicitly marked as `source_type = legacy_docx`.

## Why turn reconstruction remains conservative

The source DOCX is the evidence. Headings, tables, text style, paragraph gaps, language, and alternation may all become parser signals, but no single one is strong enough to justify silently assigning roles across the corpus.

The current Phase-2 parser therefore preserves blocks first and inference second. Assistant-like openings can mark a document as probably starting mid-conversation, but the blocks themselves remain `role = unknown` until a stronger reconstruction layer is validated.

## Later migration work

After the intermediate representation has been validated against the real corpus:

1. add stronger multi-signal User/Assistant reconstruction with auditable confidence;
2. explicitly represent unresolved/missing attachment references when visible in the DOCX;
3. decide the durable storage location for immutable legacy originals and derived IR;
4. extend the index schema so modern ChatGPT exports and legacy DOCX imports share search and organization without pretending they have identical provenance;
5. add GUI import/preview/reparse support;
6. only then consider a derived canonical search representation for legacy data.

No legacy migration should weaken the existing non-destructive archive invariants.
