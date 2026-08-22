# Architecture

GPT Exporter is organized as three cooperating layers over the same local archive.

## Archiver / Exporter

The archiver is responsible for durable preservation and human-readable exports.

Data flow:

```text
Authenticated ChatGPT tab
        |
        v
collect_chatgpt_archive.js
        |
        v
chatgpt-archive-source.json
        |
        v
import_browser_bundle.py
        |
        +--> downloads\*.json.xz   (canonical conversation data)
        +--> assets\*              (canonical preserved assets)
        |
        v
export_markdown.py / export_docx.py
        |
        +--> DOCX / optional Markdown (derived)
        |
        v
audit_asset_references.py
```

The archiver is intentionally cumulative and conservative. Absence from a later browser bundle is not permission to delete older archived data.

## Indexer

`index_chatgpt_archive.py` reads the canonical archive and produces a disposable SQLite database with FTS5 search plus organizational metadata.

The index stores derived conversation/message information and user-managed categories, tags, origin labels, and work-project assignments. The canonical ChatGPT archive remains outside SQLite.

## Archive Browser

`archive_browser.py` is a Tkinter application backed by `archive_core.py` and the SQLite index.

The browser provides search, filtering, project organization, previews, and links to generated DOCX files. It does not rewrite canonical JSON/XZ conversation data or archived assets.

## Data authority

The authority order is deliberately simple:

1. `downloads\*.json.xz` and `assets\*` are canonical durable archive data.
2. DOCX and Markdown are derived readable representations.
3. SQLite is a derived search/organization index.
4. Browser caches, manifests, and reports are optimizations or diagnostics.

No derived layer should silently normalize, delete, or replace canonical archive data.

## Versioning rule

v2.7 is the current frozen behavioral baseline. Future changes that affect canonical data, cumulative behavior, asset collection, deletion, message visibility, or conservative link resolution require explicit changelog entries and migration/rollback consideration.
