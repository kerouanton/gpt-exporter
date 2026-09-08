# Discord provider

Status: guided browser collection + canonical archive workflow.

## Normal workflow

Selecting **Discord** in the provider chooser opens a provider-owned archive window. No Discord data-package download is required.

1. Click **Open Discord** and select the DM to archive in the normal authenticated browser session.
2. Click **Start Archive…**. The validated browser collector JavaScript is copied to the clipboard and the application starts watching the standard Windows Downloads directory.
3. In Discord press **F12**, open **Console**, paste with **Ctrl+V**, and run the collector.
4. The provider detects the new `discord-dm-export-v15_*.json`, validates it, normalizes both participants into the shared canonical model, and archives the conversation automatically.

The collector is ported from `kerouanton/discord-exporter`. It traverses Discord's virtualized DM history, preserves author identity/self detection, message text, replies, reactions, links, attachments, stickers and external preview/media references. The application never reads Discord tokens, passwords, cookies, or browser profiles.

## Archive layout

The provider owns its default archive location:

```text
%USERPROFILE%\Documents\Discord Archive\
├── Discord DM <channel-id>.docx
├── downloads\
│   └── discord_dm_<channel-id>.json.xz
├── raw\
│   └── discord_dm_<channel-id>.json
└── conversations-index.sqlite
```

`raw/*.json` is copied byte-for-byte from the collector download. `downloads/*.json.xz` is the provider-neutral canonical conversation. DOCX and SQLite are derived and rebuildable.

A newly collected DM may replace the existing canonical source only when every previously archived message ID is still present. A partial collector run therefore cannot silently shrink the archive.

## Canonical mapping

- current user's messages: `role = "user"`
- other participant's messages: `role = "other"`
- unresolved authors: `role = "unknown"`
- Discord display names are preserved in `author_name`
- attachment/media URLs become `CanonicalAsset.source_ref`
- replies, reactions, mentions, content types and Discord-specific diagnostics remain provider/message metadata

The provider-neutral Markdown renderer uses `author_name` when available and retains canonical asset references as links, so Discord DOCX exports show real participant names instead of pretending the conversation is a ChatGPT-style user/assistant exchange.

## Native Discord data packages

The earlier native data-package JSON/CSV adapter remains supported as a compatibility ingestion path, but it is no longer the normal UI workflow. The guided browser collector is the primary integration because it captures both sides of the currently displayed DM.

## Boundary

Everything specific to Discord collection, normalization, paths and archive policy remains under `gpt_exporter/providers/discord`. Shared core/index/export code has no dependency on Discord, and ChatGPT archive behavior is unchanged.
