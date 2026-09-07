# Legacy DOCX import and reconstruction

Historical ChatGPT conversations may exist only as `.docx` files created by copying ChatGPT pages into Word. They are not native ChatGPT JSON exports and are handled through a separate, non-destructive legacy pipeline.

For native conversations, JSON/XZ remains the durable source and DOCX is derived. For legacy conversations, the historical DOCX remains the immutable authoritative source; SQLite, normalized turns, exported assets and normalized DOCX files are derived and rebuildable.

## Canonical storage

Legacy data lives below the ordinary ChatGPT Archive root:

```text
%USERPROFILE%\Documents\ChatGPT Archive\legacy\
├── sources\
│   └── *.docx                         # immutable historical DOCX sources
├── normalized-docx\
│   ├── * [normalized].docx           # derived modern DOCX files
│   └── assets\legacy\...             # extracted derived assets
└── reconstruction\
    ├── legacy-docx-turns.json         # normalized searchable turns
    ├── legacy-semantic-audit.json     # final semantic audit
    └── legacy-semantic-audit.csv
```

These paths are derived by `gpt_exporter.paths.default_legacy_paths()` and perform no filesystem changes merely by being imported.

The standard default locations are therefore:

```text
Sources:        %USERPROFILE%\Documents\ChatGPT Archive\legacy\sources
Normalized:     %USERPROFILE%\Documents\ChatGPT Archive\legacy\normalized-docx
Reconstruction: %USERPROFILE%\Documents\ChatGPT Archive\legacy\reconstruction
Turns JSON:     %USERPROFILE%\Documents\ChatGPT Archive\legacy\reconstruction\legacy-docx-turns.json
```

CLI path options remain available as explicit overrides for maintenance, testing and alternate archives.

## Safety invariants

- historical source DOCX files are never modified or overwritten;
- source SHA-256 is the stable identity for a legacy conversation;
- ambiguous role regions remain `unknown` rather than being guessed;
- normalized legacy DOCX files are presentation derivatives only;
- missing attachments are never invented;
- embedded assets are copied without altering source bytes;
- the final DOCX is rendered through the normal GPT Exporter Markdown-to-DOCX engine;
- exact historical pagination and Word-only layout are intentionally not reproduced.

## Validated corpus

The migration corpus contains 42 historical DOCX conversations. The validated reconstruction contains:

```text
User turns:      304
Assistant turns: 311
Unknown turns:    39
Total turns:     654
```

The final `legacy-canonical-docx-v10` corpus was rebuilt successfully, all 42 normalized DOCX files passed semantic audit v5, and all 42 were manually opened and visually checked. One embedded image was recovered with no unresolved embedded relationship.

## Current versions

```text
Word IR schema:          gpt-exporter-legacy-conversation-v3
Role inference:          legacy-role-inference-v3
Turn builder:            legacy-turn-builder-v2
Turns schema:            gpt-exporter-legacy-turns-v2
Asset exporter:          legacy-asset-export-v1
Canonical DOCX renderer: legacy-canonical-docx-v10
Semantic audit:          gpt-exporter-legacy-semantic-audit-v5
```

## Archived maintenance tools

The one-time reconstruction project is complete. Its command-line and diagnostic scripts are retained under `tools/legacy/` instead of the repository root. Run them from the repository root with `py -m tools.legacy.<module>`.

The reusable `gpt_exporter.legacy` package remains part of the application because it contains indexing/import and rendering support for legacy conversations already present in the archive.

## Normal maintenance workflow

Once the canonical archive layout exists, routine commands no longer need `F:\GPT`, a turns JSON in the repository, or an output directory in the working tree.

### Validate the legacy import

```powershell
py -m tools.legacy.import_legacy_docx_turns
```

Dry-run remains the default. To apply:

```powershell
py -m tools.legacy.import_legacy_docx_turns --apply
```

The command defaults to the canonical turns JSON and source DOCX directories. `--docx-root`, `--database` and an explicit positional turns JSON can still override them.

### Rebuild normalized DOCX derivatives

```powershell
py -m tools.legacy.build_legacy_canonical_docx --overwrite
```

This reads the canonical turns JSON and immutable legacy sources, then writes to the canonical `legacy\normalized-docx` directory. Existing output is preserved unless `--overwrite` is supplied.

### Rebuild the complete SQLite index including legacy conversations

```powershell
py -m tools.legacy.rebuild_archive_with_legacy
```

This is a dry-run validation. To perform the rebuild:

```powershell
py -m tools.legacy.rebuild_archive_with_legacy --apply
```

The native archive paths keep their normal defaults and the legacy turns/source paths use the canonical legacy subtree.

### GUI import

```powershell
py -m tools.legacy.legacy_import_gui
```

The GUI opens with the canonical turns JSON and source DOCX directory already selected. Paths remain editable when an alternate archive is intentionally being used.

## Reconstruction pipeline

```text
immutable historical DOCX
        -> Word IR v3
        -> conservative role inference v3
        -> normalized turns v2
        -> SQLite / FTS5 + provenance
        -> source-assisted Word-to-Markdown recovery
        -> asset extraction
        -> standard Markdown-to-DOCX renderer
        -> normalized DOCX v10
```

Representable semantics include headings, lists, direct and character-style bold/italic, hyperlinks, meaningful line breaks, real tables and recoverable embedded assets. Historical malformed raw-Markdown fences found inside Word paragraphs are contained locally so they cannot consume later conversation content.

## Historical reconstruction commands

The lower-level corpus tools remain available under `tools/legacy/` for diagnostics or a future parser/inference migration:

```text
py -m tools.legacy.scan_legacy_docx
py -m tools.legacy.build_legacy_docx_ir
py -m tools.legacy.profile_legacy_docx_ir
py -m tools.legacy.classify_legacy_docx_ir
py -m tools.legacy.build_legacy_docx_turns
py -m tools.legacy.verify_legacy_index
py -m tools.legacy.audit_legacy_semantic_parity
py -m tools.legacy.diagnose_legacy_emphasis
```

They are maintenance/research tools, not part of the normal product surface. Intermediate IR/profile/classification JSON can be regenerated and need not be retained after a validated migration.

## Source retention

Do not delete `legacy\sources` merely because normalized DOCX output exists. The historical DOCX files remain the authoritative evidence for future parser, role-inference, asset-extraction or renderer improvements. Derived normalized DOCX, assets, SQLite rows and reconstruction JSON may be regenerated from those sources.
