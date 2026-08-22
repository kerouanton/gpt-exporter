# GPT Exporter

GPT Exporter is a Windows-oriented toolkit for preserving, exporting, indexing, and browsing a local ChatGPT conversation archive.

The project combines three related tools:

- **Archiver / Exporter** — collects conversations from an authenticated ChatGPT browser session, stores cumulative canonical JSON/XZ plus assets, and generates readable DOCX or Markdown exports.
- **Indexer** — builds a disposable SQLite FTS5 index over the local archive, including conversation provenance, categories, tags, and user-defined work projects.
- **Archive Browser** — a Tkinter GUI for searching, filtering, organizing, and opening indexed conversations.

Current development line: **v2.7**.

> [!IMPORTANT]
> GPT Exporter processes private conversation data and browser-session material. Never publish your generated archive, browser bundle, SQLite index, cookies, tokens, or private attachments. See `SECURITY.md`.

## Status

v2.7 is the current frozen behavioral baseline. The repository continues development from that baseline while preserving the archive invariants documented in `FROZEN_VERSION.md` and `CHANGELOG.md`.

The original v2.7 ZIP validation manifest is retained in `SOURCE_SHA256SUMS.txt` for historical identification. It describes the original frozen package, **not** the current Git checkout after repository-publication preparation.

## Requirements

- Windows 10 or later is the primary tested platform.
- Python 3.12 or newer.
- Firefox is the documented browser workflow for the collector.
- Python dependencies listed in `requirements.txt` / `pyproject.toml`.

Install dependencies:

```text
py -m pip install -r requirements.txt
```

Optional environment check:

```text
py check_environment.py
```

## Quick start — Archiver / Exporter

### 1. Generate the browser bundle

1. Open `https://chatgpt.com/` in Firefox and sign in to the account you want to archive.
2. Press `F12` and open the **Console** tab.
3. Open `collect_chatgpt_archive.js` locally and review it before running it.
4. Paste the complete script into the ChatGPT Console and execute it.
5. Wait for Firefox to download:

```text
chatgpt-archive-source.json
```

The collector uses the already authenticated browser session. The temporary bundle may contain complete private conversations and assets, so keep it private.

### 2. Run the cumulative archive

Leave the bundle in the normal Windows Downloads directory and run:

```text
py archive_chats.py
```

The default archive location is:

```text
%USERPROFILE%\Documents\ChatGPT Archive\
```

A successful normal run keeps canonical conversation sources under `downloads\*.json.xz`, preserves assets under `assets\`, generates root-level DOCX files, and removes the consumed temporary browser bundle from Downloads.

The archive is cumulative: an older local conversation or asset is not deleted merely because it is absent from a later browser bundle.

### Useful archive commands

Rebuild all derived DOCX files from the existing local JSON/XZ archive:

```text
py archive_chats.py --convert-only
```

Generate persistent Markdown explicitly:

```text
py export_all.py --markdown-only --overwrite-all
```

Skip media inventory for one run:

```text
py archive_chats.py --skip-assets
```

Destructive reset:

```text
py archive_chats.py --fresh
```

`--fresh` deletes the generated local archive tree before importing the current bundle. It is **not** intended for routine use.

## Quick start — Indexer

Build or update the SQLite search index:

```text
py index_chatgpt_archive.py index
```

The default database is:

```text
%USERPROFILE%\Documents\ChatGPT Archive\conversations-index.sqlite
```

The index is derived data and can be rebuilt from the canonical archive. The schema supports:

- full-text search with SQLite FTS5;
- standard / Custom GPT / Project provenance detection;
- multiple categories per conversation;
- multiple tags per conversation;
- multiple user-defined work projects per conversation;
- origin labels and filtering;
- dry-run-first bulk organization commands.

Use the command help for the complete CLI:

```text
py index_chatgpt_archive.py --help
```

## Quick start — Archive Browser

After creating the SQLite index, run:

```text
py archive_browser.py
```

The browser provides:

- full-text search;
- origin, project, tag, and category filters;
- sortable conversation lists;
- project-tree organization and drag-and-drop assignment;
- conversation details and matching-message previews;
- direct DOCX opening and reveal-in-file-manager actions;
- a lightweight keyword/tag cloud.

The GUI modifies only the SQLite organizational metadata. It does not rewrite canonical archived JSON/XZ or DOCX files.

## Archive model and preservation invariants

The following rules are intentionally conservative:

1. Canonical durable data is `downloads\*.json.xz + assets\*`.
2. DOCX, Markdown, SQLite indexes, manifests, and reports are derived/rebuildable.
3. Normal archiving is cumulative and non-destructive.
4. Existing assets are never pruned merely because a later bundle does not reference them.
5. Asset collection is deliberately broad; over-collection is safer than silently losing recoverable files.
6. The ChatGPT `file_id` embedded in archived filenames is the stable join key for local assets.
7. Unsupported raster formats may be normalized in memory for DOCX embedding, but original archived assets are never rewritten for compatibility.
8. Ambiguous historical `sandbox:/mnt/data/...` links are never resolved by guessing.
9. Missing visible attachments are represented explicitly rather than silently substituted.
10. Changes that affect canonical data, deletion policy, collection breadth, visible-role semantics, or local-link semantics require explicit documentation and migration/rollback consideration.

See `FROZEN_VERSION.md` for the v2.7 acceptance record.

## Main files

| File | Purpose |
|---|---|
| `collect_chatgpt_archive.js` | Browser-side collector for conversations and browser-accessible assets |
| `archive_chats.py` | Main cumulative archive workflow |
| `import_browser_bundle.py` | Imports the temporary browser bundle into the persistent archive |
| `inventory_media.py` | Inventories media references |
| `build_asset_manifest.py` | Builds cumulative asset-reference diagnostics |
| `build_browser_asset_cache_seed.py` | Seeds the optional Firefox asset cache from an existing local report |
| `export_all.py` | Coordinates Markdown/DOCX export and cumulative asset audit |
| `export_markdown.py` | Converts archived conversation JSON/XZ to Markdown |
| `export_docx.py` | Converts Markdown to DOCX and preserves local asset links |
| `audit_asset_references.py` | Audits physical asset/reference consistency without deleting data |
| `index_chatgpt_archive.py` | SQLite FTS5 indexer and organization CLI |
| `archive_core.py` | Shared data/query core for the Archive Browser |
| `archive_browser.py` | Tkinter archive browser and organizer |
| `check_environment.py` | Checks runtime dependencies and active pipeline files |

## Privacy

Generated archive data is intentionally excluded by `.gitignore`. In particular, do not commit:

- `chatgpt-archive-source.json`;
- conversation JSON/XZ files;
- downloaded assets or attachments;
- generated DOCX/Markdown containing private conversations;
- `conversations-index.sqlite` or its WAL/SHM files;
- browser cookies, access tokens, account IDs, or authorization headers.

See `SECURITY.md` for reporting guidance.

## Development

Run the test suite with:

```text
py -m unittest discover -s tests -v
```

GitHub Actions validates supported Python versions on Windows.

See `CONTRIBUTING.md` before changing archive semantics.

## Historical release material

- `CHANGELOG.md` — release lineage and behavior changes.
- `FROZEN_VERSION.md` — historical v2.7 validation record and preservation baseline.
- `SOURCE_SHA256SUMS.txt` — hashes from the original frozen v2.7 ZIP package; retained unchanged as historical evidence and not intended to match the evolving Git repository checkout.

## License

GPT Exporter is free software licensed under **GNU GPL v3 or later (`GPL-3.0-or-later`)**. See `LICENSE`.
