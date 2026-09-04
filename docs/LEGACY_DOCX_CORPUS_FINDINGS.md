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

## Phase 2 direction

Recommended next parser stage:

1. preserve the original DOCX unchanged and hash it;
2. extract ordered blocks (paragraphs, tables, links, embedded-object references) instead of flattening to plain text;
3. classify block features such as style, indentation, spacing, table adjacency, heading density, hyperlinks, and list/code characteristics;
4. infer candidate turn boundaries with confidence scores rather than binary rules;
5. assign roles only when evidence is strong enough;
6. allow `unknown` role blocks and `starts_mid_conversation=true` when the beginning cannot be reconstructed safely;
7. keep a full-text fallback so every legacy document remains searchable even when turn reconstruction is partial;
8. only after corpus validation, synthesize the canonical derived representation and connect it to SQLite/FTS5.

The corpus confirms that legacy DOCX import is viable, but it should be modeled as provenance-preserving reconstruction rather than a lossless conversion from native ChatGPT export data.
