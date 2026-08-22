# Contributing to gpt-exporter

Thanks for your interest in gpt-exporter.

## Development principles

The local archive is cumulative and non-destructive. Canonical durable data is the archived conversation JSON/XZ plus preserved assets; DOCX, Markdown, indexes, manifests, and reports are derived and rebuildable.

Changes must not silently delete, prune, normalize, or replace canonical archive data. Ambiguous asset mappings must remain unresolved rather than being guessed.

## Development setup

Use Python 3.12 or newer.

```text
python -m pip install -r requirements.txt
```

Before submitting a change, compile all Python sources and run any tests relevant to the modified code.

## Pull requests

Keep changes focused. Describe behavioral changes, archive-format implications, and migration or rollback requirements where applicable. Changes affecting canonical data, cumulative behavior, deletion policy, visible-message semantics, or asset-link semantics require explicit documentation.

Do not commit personal ChatGPT archives, browser bundles, SQLite indexes, generated exports, downloaded assets, credentials, cookies, access tokens, or local IDE state.

## License

By contributing, you agree that your contribution is licensed under GPL-3.0-or-later, the same license as the project.
