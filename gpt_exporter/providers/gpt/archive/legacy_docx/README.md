# Archived ChatGPT legacy DOCX migration

This directory is a historical snapshot of the completed ChatGPT DOCX migration.

The real corpus cutover was validated on 2026-09-07:

- 42 conversations
- 654 messages
- 304 user
- 311 assistant
- 39 unknown
- 42 canonical GPT sources
- 0 DOCX dependencies in a clean temporary rebuild
- cutover status: PASS

The authoritative runtime data is now the canonical provider JSON/XZ stored under the normal archive `downloads` tree. Historical DOCX files and the DOCX parser/reconstruction/audit pipeline are no longer required for indexing or rebuild.

## Snapshot layout

`./snapshot/` contains exact historical source blobs retained only for archaeology, rollback analysis, or provenance. Python sources are intentionally stored as `*.py.txt` so they are not importable modules, not executed by normal test discovery, and not part of the active runtime surface.

The snapshot includes:

- the former `gpt_exporter/legacy/` package;
- former repository-root legacy migration scripts;
- legacy-specific tests;
- migration documentation;
- the one-time canonical promotion and cutover verification tools.

## Architectural status

Legacy DOCX is not a core capability and not an active ChatGPT-provider capability. It is closed migration history.

The provider-neutral engine must not import or depend on this archive. Normal operation must remain valid if this directory is removed entirely.
