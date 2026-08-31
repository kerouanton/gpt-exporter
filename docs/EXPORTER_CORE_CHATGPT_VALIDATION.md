# Exporter CORE — ChatGPT formal validation record

Status: **VALIDATED / FROZEN MILESTONE**  
Validation date: **2026-08-31**  
Branch: `architecture/exporter-core`  
Pull request: `#25`  
Planned milestone tag: `exporter-core-chatgpt-validated-2026-08-31`

This record closes the ChatGPT phase of the exporter-core refactor. It is not a
new public application release and does not change the existing `2.9.0` product
version. Its purpose is to provide a stable, reviewable Git milestone before a
second provider is integrated.

## Acceptance rule

The refactor was accepted only under the rule:

> New architecture, same ChatGPT results.

For the same preserved native ChatGPT source, unexplained differences in
canonical preservation, `current-batch`, message selection/order, searchable
text, Markdown, DOCX, provenance, Projects/Tags/Categories, archive layout, or
incremental behavior were treated as regressions.

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

## Real-archive validation evidence

The final explicit compatibility run was executed on the existing Windows
ChatGPT archive with:

```text
py -m gpt_exporter.validation_cli
```

It used `reports/current-batch.json` and compared:

- the production CORE SQLite database;
- a separate shadow CORE SQLite database;
- the historical ChatGPT indexer as a legacy oracle;
- CORE Markdown against historical Markdown;
- production DOCX against a historical DOCX oracle.

Final result:

```text
Provider    : ChatGPT
Sources     : 2
Checked     : 2
Matched     : 2
Mismatched  : 0
Failed      : 0
```

The behavioral validation was performed on branch commit
`ee2062ad1570563b628e8aafbe5b56bfa9af4cac` before the final dead-code and
documentation cleanup. The cleanup is constrained to obsolete workflow seams and
documentation and must itself have a fully green test/build CI before the
milestone tag is created.

Earlier real-archive validation during the same refactor also established zero
differences for normalized message/title/index content and native ChatGPT
provenance/origins.

## DOCX comparison rule

DOCX equality is structural/semantic rather than a blind ZIP byte comparison.
Volatile package metadata is ignored. Local OOXML relationship targets are
resolved against each DOCX location before comparison, so two relative paths
that resolve to the same archived asset are equal. Tests also verify that
relationships resolving to different assets remain mismatches.

This removes the false mismatch caused when the production DOCX lives at the
archive root while the legacy oracle DOCX lives below
`reports/provider-validation/...`.

## Performance acceptance

Two expensive diagnostics were intentionally removed from the normal archive
path after real timing tests:

- cumulative asset-reference audit;
- full CORE/shadow/legacy compatibility validation.

Both remain available explicitly. The normal incremental index also checks the
stored source path and mtime before provider normalization, so unchanged
conversations are skipped without reconstructing their full normalized model.

This preserves the diagnostic capability without charging its full-archive cost
on every daily archive update.

## Cleanup performed for the milestone

The obsolete root `archive_gui_workflow.py` implementation was removed after the
main GUI had fully migrated to `gpt_exporter.ui.WorkspaceArchiveRunDialog` and
`WorkspaceWorkflow`. Its dedicated tests were removed with it. The now-unused
`CHATGPT_WORKFLOW` singleton was also removed.

The following compatibility seams are deliberately retained and are **not dead
code** at this milestone:

- root command-line wrappers such as `archive_chats.py`, `export_all.py`,
  `export_markdown.py`, `export_docx.py`, and `index_chatgpt_archive.py`;
- packaged `_legacy_*` implementations used to preserve historical behavior and
  provide compatibility/oracle coverage;
- `ProviderWorkflow` as the provider-level non-GUI workflow used underneath
  `WorkspaceWorkflow`;
- the ChatGPT-specific guard in `provider_pipeline.py`, which prevents an
  unimplemented provider from modifying an archive before its complete pipeline
  semantics exist.

Removing any of these merely because its name contains `legacy` would weaken the
compatibility contract rather than clean the architecture.

## Canonical preservation invariants

The milestone does not alter the established archive authority model:

```text
downloads/*.json.xz + assets/*   canonical durable source
DOCX / Markdown                  derived / rebuildable
SQLite / FTS                     derived search + organization index
reports / manifests / caches    diagnostics or optimizations
```

Normal updates remain cumulative and non-destructive. A later bundle does not
implicitly delete an older conversation or asset. Ambiguous local links are not
guessed. Browser-managed Projects, Tags and Categories survive incremental
indexing.

## CI gate for the tag

The milestone tag may point only at a commit for which both pull-request
workflows complete successfully:

- `Tests` — Python 3.12 and 3.13;
- `Windows onedir build`.

The PR must remain unmerged until a separate merge decision is made.

## Scope boundary

This validation freezes only the **ChatGPT provider on exporter CORE**. It does
not claim that Discord is integrated or validated. Discord is intentionally the
next architecture test: its provider must reuse the same workspace UI, GUI,
search/organization, normalized model, Markdown/DOCX path and SQLite/FTS core
instead of recreating a second application.
