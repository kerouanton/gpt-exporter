# Legacy DOCX maintenance tools

The one-time legacy DOCX reconstruction project is complete. These scripts are retained only for maintenance, recovery, audit, or a future renderer migration; they are intentionally kept out of the repository root.

Run tools from the repository root as modules, for example:

```powershell
py -m tools.legacy.build_legacy_canonical_docx --overwrite
py -m tools.legacy.import_legacy_docx_turns
py -m tools.legacy.audit_legacy_semantic_parity
```

The canonical data layout remains:

```text
%USERPROFILE%\Documents\ChatGPT Archive\legacy\
    sources\
    normalized-docx\
    reconstruction\
```

The historical DOCX files in `sources` remain authoritative and immutable. The `gpt_exporter.legacy` package remains part of the application because it contains reusable runtime/indexing support; only the completed migration/reconstruction command-line tooling is archived here.
