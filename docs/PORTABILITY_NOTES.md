# Portability notes

The public-release branch keeps the existing Windows archive convention:

```text
%USERPROFILE%\Documents\ChatGPT Archive
```

The default paths used by both `index_chatgpt_archive.py` and `archive_browser.py` are now derived from `USERPROFILE`, with `Path.home()` as a fallback. This matches the pattern already used by the archiver and environment-check scripts and removes the dependency on a literal developer profile path.

The effective Windows defaults remain:

```text
%USERPROFILE%\Documents\ChatGPT Archive
%USERPROFILE%\Documents\ChatGPT Archive\conversations-index.sqlite
```

This is a portability change only. It does not alter archive layout, database naming, migration behavior, or preservation semantics.
