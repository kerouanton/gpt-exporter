# Legacy DOCX corpus findings

Initial corpus audit performed against the user's historical DOCX archive in `F:\GPT`.

## Corpus summary

- 42 DOCX files scanned successfully.
- Categories parsed from normalized filenames:
  - HAM: 21
  - PKI: 19
  - EMBEDDED: 1
  - IT: 1
- Approximate preserved document structure across the corpus:
  - 51,424 paragraphs
  - 596 tables
  - 8,587 headings
- 41 files reported medium structural confidence; one file (`HAM GPT 2026-04-03 BOM transverter 3.2-20 GHz.docx`) reported low confidence because it preserves no tables or heading styles.

## Important finding: first visible message is not always a User turn

The Phase 1 scanner originally exposed `likely_first_user_message`. Corpus-level evidence shows that assumption is unsafe.

Several documents clearly begin with an Assistant-style continuation such as:

- `Parfait, ...`
- `Très bonne question ...`
- `Bonne idée ...`
- `Ton intuition est bonne ...`
- `Tu as fait exactement ce qu’il faut ...`

This means some Word copies start in the middle of a ChatGPT conversation or were captured from a scrolled/partial page. The first visible block must therefore be treated as role-unknown evidence until stronger structural signals are available.

## Boundary heuristic finding

The current double-blank-gap heuristic is useful only as an audit signal. Across the corpus the median boundary-candidate count is 1, while the maximum is 16. Long conversations can contain many genuine turns but also rich-content transitions that produce similar gaps.

Therefore:

- boundary candidates must not directly become User/Assistant turns;
- role assignment needs multiple independent signals;
- incomplete starts must be explicitly representable;
- unstructured fallback indexing must remain possible.

## Validated reconstruction result

The corpus has been reconstructed into 654 normalized turns:

```text
User:      304
Assistant: 311
Unknown:    39
Total:     654
```

The 42 historical DOCX sources have been imported successfully into the normal SQLite/FTS5 browser path. The original DOCX files remain immutable authoritative sources.

## Media-preservation phase

The normalized-DOCX renderer now performs source-assisted media recovery before using the normal GPT Exporter Markdown-to-DOCX renderer.

Current path:

```text
legacy turn JSON + immutable source DOCX
    -> restored Word block text
    -> embedded relationship extraction
    -> derived asset files
    -> Markdown local image/attachment references
    -> standard Markdown-to-DOCX renderer
```

The extractor recognizes:

- DrawingML inline images;
- historical VML image relationships;
- embedded OLE/package relationships when the payload is physically present in the DOCX package.

Assets are content-addressed and stored below the normalized output directory so repetitive Word package names such as `image1.png` cannot collide across conversations.

The next corpus-level acceptance pass must compare all 42 historical DOCX files with their regenerated `[normalized].docx` derivatives and record at least:

- source vs regenerated image counts;
- exported embedded-attachment counts;
- unresolved embedded relationship counts;
- text/turn reconstruction differences already visible during manual review;
- any external attachment links whose original bytes are not present in the Word package.

A link to a historical attachment is not evidence that the attachment bytes are embedded in Word. Missing bytes must never be invented; the historical DOCX remains authoritative when recovery is impossible.

## Preservation direction

The legacy pipeline should continue to follow these rules:

1. preserve the original DOCX unchanged and hash it;
2. preserve ordered Word evidence separately from role inference;
3. infer roles conservatively and retain `unknown` regions;
4. keep normalized turns as a versioned JSON-derived representation;
5. recover physically embedded assets without rewriting the source;
6. feed reconstructed Markdown through the same DOCX renderer used by native GPT Exporter output;
7. keep exported assets and normalized DOCX files derived/rebuildable;
8. validate the full corpus before declaring media parity complete.

The corpus confirms that legacy DOCX import is viable, but it must remain provenance-preserving reconstruction rather than pretending to be a lossless native ChatGPT export conversion.
