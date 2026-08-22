# Portability notes

The public-release branch intentionally keeps the existing Windows archive convention:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

Two modules still need a small cleanup before publication:

- `index_chatgpt_archive.py`
- `archive_browser.py`

Their current defaults contain a literal developer profile path. The intended replacement is to derive the same location from `USERPROFILE` with `Path.home()` as a fallback, matching the existing pattern already used by the archiver and environment-check scripts.

This is a portability change only. It must not alter archive layout, database naming, migration behavior, or any preservation semantics.
