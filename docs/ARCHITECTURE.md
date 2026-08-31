# Architecture

GPT Exporter is a provider-driven archive application built around one common
CORE. The ChatGPT provider is the reference implementation formally validated on
2026-08-31; additional providers must reuse the same CORE rather than duplicate
the application.

## Runtime context: Workspace

The GUI operates on one `Workspace` at a time:

```text
Workspace
    provider
    archive_root
    database
```

`WorkspaceWorkflow` is the GUI's single runtime workflow context. Switching
workspace switches provider, archive root, SQLite database, collector/source
bundle lookup, archive execution and index update together.

A Provider and a Workspace are deliberately different concepts. A provider
contains source-specific behavior; a workspace chooses one archive instance for
that provider. Multiple workspaces may therefore use the same provider while
remaining physically separate.

## Provider boundary

A provider owns only source-specific behavior:

- identity, website and source-bundle name;
- collector/acquisition mechanism;
- native source parsing/import preservation;
- source-specific attachment/reference semantics;
- normalization into the common conversation model;
- source-specific provenance/origin detection;
- genuinely provider-specific actions.

Providers do **not** own their own GUI, search engine, project/tag/category
system, keyword cloud, archive layout, generic Markdown/DOCX renderer or generic
SQLite/FTS writer.

## Normalized CORE flow

```text
provider-native source
        |
        v
provider importer / canonical preservation
        |
        v
provider normalizer
        |
        v
common Conversation model
        |
        +--> display projection --> CORE Markdown --> common DOCX converter
        |
        +--> search projection  --> CORE SQLite / FTS
        |
        +--> Browser / Search / Projects / Tags / Categories / Keywords
```

ChatGPT requires separate display and search projections for historical
compatibility. Markdown/DOCX follows the active visible branch, while the search
projection reproduces the established index semantics. CORE consumes those
normalized projections and does not interpret ChatGPT-native JSON itself.

## Archive pipeline

The normal ChatGPT workflow remains five visible stages:

```text
1/5 - Import ChatGPT archive bundle
2/5 - Inventory media references
3/5 - Build asset manifest
4/5 - Export new or larger conversations
5/5 - Update archive search index
```

Stages 4 and 5 are production CORE stages. Expensive whole-archive diagnostics,
including the cumulative asset-reference audit and full CORE/legacy oracle, are
explicit opt-in diagnostics rather than part of every incremental run.

## Data authority

The authority order remains conservative:

1. `downloads/*.json.xz` and `assets/*` are canonical durable provider source.
2. DOCX and Markdown are derived/readable representations.
3. SQLite/FTS is a derived search index with user-managed organization metadata.
4. Reports, manifests and caches are diagnostics/optimizations.

No derived layer may silently delete, normalize or replace canonical archive
data. Normal updates remain cumulative and non-destructive.

## Compatibility layers deliberately retained

Historical root CLI wrappers remain available for diagnostics and advanced use.
Packaged `_legacy_*` modules are retained where they still encode frozen behavior
or serve as compatibility oracles. Their presence is intentional and is not a
second application architecture.

The obsolete root `archive_gui_workflow.py` implementation was removed after the
main GUI migrated fully to `WorkspaceWorkflow` and the package UI.

## Validation status

The ChatGPT exporter CORE milestone is formally validated on the complete real
archive. On 2026-08-31 the command:

```text
py -m gpt_exporter.validation_cli --all
```

ran against 146 archived conversations and produced:

```text
Checked     : 146
Matched     : 146
Mismatched  : 0
Failed      : 0
```

The validation covered production CORE versus shadow CORE and the historical
legacy oracles, including message content, provenance/origins, Markdown and
semantic DOCX comparison.

During the full gate, the validator was corrected to regenerate both CORE and
legacy DOCX in its disposable validation tree, and the ChatGPT normalizer was
corrected so visible legacy roles take precedence over native internal tool names
for presentation. A `--mismatched` mode now supports targeted retesting without
rerunning the complete archive.

The milestone tag is:

```text
exporter-core-chatgpt-validated-2026-08-31
```

The exact tag-target commit must have green Python 3.12/3.13 tests and Windows
onedir build CI. The PR remains draft and unmerged until a separate merge decision
is made.

See `EXPORTER_CORE_CHATGPT_VALIDATION.md` for the formal freeze/tag record and
`EXPORTER_CORE_ARCHITECTURE.md` for the detailed provider/workspace contract.

No Discord integration is included in the ChatGPT validation milestone.
