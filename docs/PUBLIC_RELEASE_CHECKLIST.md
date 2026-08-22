# Public release checklist

This checklist tracks the work required before changing the repository from private to public.

## Completed

- [x] Normalize project version numbering to v2.7.
- [x] Rename the indexer to `index_chatgpt_archive.py`.
- [x] Add GPL-3.0-or-later licensing metadata.
- [x] Add `pyproject.toml`.
- [x] Add contribution guidance.
- [x] Add security/privacy guidance.
- [x] Add Windows GitHub Actions validation on Python 3.12 and 3.13.
- [x] Add initial indexer smoke tests.
- [x] Rewrite the public-facing README around Archiver / Indexer / Archive Browser.
- [x] Clarify that `SOURCE_SHA256SUMS.txt` identifies the original frozen v2.7 package rather than the evolving Git checkout.
- [x] Make the default Indexer and Archive Browser paths portable while preserving the current Windows default archive location.
- [x] Add focused tests for the portable default paths.
- [x] Review code and documentation for obvious secrets, authentication material, private archive data, and accidental generated files.
- [x] Confirm GitHub Actions is green on the release-preparation branch after the portability changes.

## Before publication

- [x] Review examples and regression notes for unnecessarily specific private conversation names.
- [x] Confirm the full GPL-3.0-or-later license text is present in the release-preparation branch.
- [x] Review the complete branch diff against `main` after the final license change.
- [ ] Merge only after local inspection.
- [ ] Re-run a complete local archive/index/browser smoke test after merge.
- [ ] Create the public release/tag only after the repository contents are accepted.

## Preservation constraints

Public-release cleanup must not silently change the canonical archive format, deletion policy, cumulative semantics, asset-collection breadth, visible-role semantics, or conservative local-link behavior documented by the v2.7 frozen baseline.
