# GPT Exporter v2.9.0 release notes

Release date: 2026-08-24

## Summary

GPT Exporter v2.9.0 is the first release line prepared for direct Windows executable distribution.

The Windows build is a self-contained PyInstaller `onedir` application. Users do not need to install Python to run it. The durable archive model is unchanged from v2.8: cumulative `downloads/*.json.xz + assets/*` remains the canonical source, while DOCX, Markdown, SQLite indexes, manifests, reports, and logs remain derived/rebuildable outputs.

## Windows distribution

The GitHub release provides:

- `GPT-Exporter-2.9.0-Windows-x64.zip` — complete self-contained Windows application directory;
- `GPT-Exporter-2.9.0-Windows-x64.zip.sha256` — SHA-256 checksum for the ZIP;
- GitHub-generated source archives for the tagged source release.

Installation is intentionally simple:

1. download the Windows ZIP from the GitHub release;
2. extract the complete archive to a directory of your choice;
3. run `GPT Exporter.exe` from the extracted `GPT Exporter` directory.

Do not move only the `.exe`: the `_internal` directory beside it contains the embedded Python runtime and packaged dependencies/resources required by the application.

The Windows executable is a GUI/windowed PE application and does not open a console window during normal use.

## Major v2.9 changes

- Refactored the reusable core into the `gpt_exporter` package while preserving v2.8 behavior.
- Added explicit library APIs for import, media inventory, manifest generation, asset auditing, Markdown export, DOCX export, batch export, incremental indexing, and complete archive orchestration.
- Removed the GUI's internal Python-subprocess cascade for the normal archive workflow; the GUI now calls the packaged pipeline in-process from a worker thread.
- Preserved Tkinter thread-safety through queue-based progress delivery to the main GUI thread.
- Converted historical command-line implementations into thin compatibility wrappers.
- Added package-closure tests to prove reusable core operation without repository-root implementation modules.
- Packaged the collector JavaScript, user guide, and release history with the application.
- Added central application version metadata, `--version`, Help/User Guide/Release History surfaces, a Markdown documentation viewer, and an About dialog.
- Added reproducible PyInstaller Windows builds with Python 3.13.
- Added Windows PE File/Product version metadata generated from the same central version source used by the GUI and project metadata.
- Added GitHub Actions validation for Python 3.12 and 3.13 plus dedicated Windows build and release automation.

## Validation

Before the final v2.9.0 release, the Windows `onedir` build was validated locally on Windows and by GitHub Actions.

Validation covered:

- direct GUI launch from `GPT Exporter.exe`;
- no console window in the normal build;
- Help, About, User Guide, and Release History;
- packaged collector JavaScript and Explorer reveal action;
- Windows PE GUI subsystem and version metadata;
- packaged non-Python resources;
- full Python unit-test suite on Python 3.12 and 3.13;
- reproducible PyInstaller packaging on GitHub-hosted Windows runners.

## Compatibility and preservation

v2.9.0 intentionally does not change the archive preservation policy established by the v2.7/v2.8 line.

The following invariants remain in force:

- normal updates are cumulative and non-destructive;
- conversations absent from a later collection bundle are not deleted;
- assets are not pruned merely because a later bundle no longer references them;
- source assets are not rewritten for DOCX compatibility;
- ambiguous historical local links are not guessed;
- the SQLite index is derived and rebuildable;
- Browser-managed project/category/tag metadata survives incremental indexing.

No archive migration is required when upgrading from v2.8.

## Known limitation

The integrated archive workflow still intentionally targets the default archive location:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

The Browser can be opened against another SQLite database, but the integrated archive workflow refuses to write through that non-default Browser instance.

The Windows executable is not code-signed, so Windows SmartScreen may display a reputation warning on some systems.

## License

GPT Exporter v2.9.0 is licensed under GNU GPL v3 or later (`GPL-3.0-or-later`). The Windows distribution includes the license text, and the tagged GitHub release provides the corresponding source tree.
