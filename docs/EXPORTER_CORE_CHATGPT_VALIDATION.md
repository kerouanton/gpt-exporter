# Exporter CORE — ChatGPT formal validation record

Status: **CANDIDATE FOR FORMAL TAG — FULL-ARCHIVE GATE PENDING**  
Validation date: **2026-08-31**  
Branch: `architecture/exporter-core`  
Pull request: `#25`  
Planned milestone tag: `exporter-core-chatgpt-validated-2026-08-31`

This record closes the implementation/cleanup phase of the ChatGPT exporter-core
refactor and defines the final gate required before the milestone tag is created.
It is not a new public application release and does not change the existing
`2.9.0` product version.

## Acceptance rule

The refactor is accepted only under the rule:

> New architecture, same ChatGPT results.

For the same preserved native ChatGPT source, unexplained differences in
canonical preservation, `current-batch`, message selection/order, searchable
text, Markdown, DOCX, provenance, Projects/Tags/Categories, archive layout, or
incremental behavior are regressions.

## Production path at the milestone

The normal GUI path is workspace-driven:

```text
Workspace
  -> Provider
  -> archive root / database
  -> provider acquisition + importer
  -> provider-normalized Conversation model
       -> CORE Markdown -> common DOCX converter
       -> CORE SQLite / FTS index
  -> common Browser / Search / Projects / Tags / Categories / Keywords
```

The main GUI uses `WorkspaceWorkflow` as its runtime context. Changing workspace
changes provider, archive root, SQLite database, collector, bundle lookup,
archive execution and search-index update together.

ChatGPT production step 4/5 (Markdown/DOCX) and step 5/5 (SQLite/FTS) both run
through the normalized CORE path.

## Real-archive validation already completed

The explicit current-batch compatibility run was executed on the existing
Windows ChatGPT archive with:

```text
py -m gpt_exporter.validation_cli
```

It compared:

- production CORE SQLite;
- separate shadow CORE SQLite;
- historical ChatGPT indexer as legacy oracle;
- CORE Markdown versus historical Markdown;
- production DOCX versus historical DOCX oracle.

Result:

```text
Provider    : ChatGPT
Sources     : 2
Checked     : 2
Matched     : 2
Mismatched  : 0
Failed      : 0
```

That behavioral run was performed on commit
`ee2062ad1570563b628e8aafbe5b56bfa9af4cac` before final dead-code/documentation
cleanup.

## Final full-archive gate

A formal Git tag requires one final real-data run over the entire preserved
ChatGPT archive after the cleanup branch is pulled:

```text
py -m gpt_exporter.validation_cli --all
```

The tag gate is:

```text
Checked == total archived conversations
Matched == Checked
Mismatched == 0
Failed == 0
```

The final full-archive result must be recorded in this document before the tag is
created. This deliberately makes the tag stronger than the previous
`current-batch` validation.

## DOCX comparison rule

DOCX equality is structural/semantic rather than a blind ZIP byte comparison.
Volatile package metadata is ignored. Local OOXML relationship targets are
resolved against each DOCX location before comparison, so two relative paths
that resolve to the same archived asset are equal. Tests also verify that
relationships resolving to different assets remain mismatches.

## Performance acceptance

Two expensive diagnostics are intentionally outside the normal archive path:

- cumulative asset-reference audit;
- full CORE/shadow/legacy compatibility validation.

Both remain explicit diagnostics. The normal incremental index checks stored
source path + mtime before provider normalization, so unchanged conversations are
skipped without reconstructing their full normalized model.

## Cleanup performed

The obsolete root `archive_gui_workflow.py` implementation was removed after the
main GUI fully migrated to `gpt_exporter.ui.WorkspaceArchiveRunDialog` and
`WorkspaceWorkflow`. Its dedicated tests were removed. A remaining collector test
was rebound to `WorkspaceWorkflow`, proving the old module was no longer a hidden
dependency. The unused `CHATGPT_WORKFLOW` singleton was also removed.

The cleanup candidate passed:

- Python 3.12 tests: success;
- Python 3.13 tests: success;
- Windows onedir build: success.

The following compatibility seams are deliberately retained and are **not dead
code**:

- root command-line wrappers such as `archive_chats.py`, `export_all.py`,
  `export_markdown.py`, `export_docx.py`, and `index_chatgpt_archive.py`;
- packaged `_legacy_*` implementations used to preserve historical behavior and
  provide compatibility/oracle coverage;
- `ProviderWorkflow` as the provider-level non-GUI workflow used underneath
  `WorkspaceWorkflow`;
- the ChatGPT-specific guard in `provider_pipeline.py`, which prevents an
  unimplemented provider from modifying an archive before its complete pipeline
  semantics exist.

Removing these merely because their names contain `legacy` would weaken the
compatibility contract rather than clean the architecture.

## Canonical preservation invariants

```text
downloads/*.json.xz + assets/*   canonical durable source
DOCX / Markdown                  derived / rebuildable
SQLite / FTS                     derived search + organization index
reports / manifests / caches    diagnostics or optimizations
```

Normal updates remain cumulative and non-destructive. A later bundle does not
implicitly delete older conversations/assets. Ambiguous local links are not
guessed. Browser-managed Projects, Tags and Categories survive incremental
indexing.

## CI gate for the tag

After the full-archive result is recorded, the exact tag-target commit must again
have both pull-request workflows green:

- `Tests` — Python 3.12 and 3.13;
- `Windows onedir build`.

The PR remains unmerged unless a separate merge decision is made.

## Scope boundary

This tag validates only **ChatGPT on exporter CORE**. It makes no claim about
Discord integration. Discord remains the next architecture test and must reuse
the same workspace UI, GUI, search/organization, normalized model,
Markdown/DOCX path and SQLite/FTS CORE.
