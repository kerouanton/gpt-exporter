# Discord provider

Status: first concrete non-ChatGPT provider / experimental ingestion UI.

## Supported source

The provider targets an extracted **native Discord data package**, specifically its `messages` section. Discord currently documents those transcripts as JSON files grouped by channel; older packages used CSV transcripts, so the provider accepts both formats.

One Discord channel transcript becomes one `CanonicalConversation` with `provider_id = "discord"`. Available channel/guild metadata is preserved as provider metadata. Message IDs, timestamps, contents, and attachment URLs are normalized into the shared canonical model.

## Important source limitation

Discord's native data package contains the messages sent by the requesting account. It is not a complete two-sided/server transcript. The provider therefore normalizes those exported messages as `role = "user"` and deliberately does not synthesize messages from other participants.

## Current UI scope

Selecting **Discord** in the application provider chooser opens a first-stage provider window. The user chooses an extracted Discord data package and clicks **Analyze**. The provider discovers transcript files, normalizes them through the same `ConversationProvider` contract used by ChatGPT, and displays conversation/message counts plus first/last timestamps.

This PR intentionally does not yet define a Discord archive destination, incremental import policy, asset downloader, or DOCX workflow. Those should be added only after validating the real Discord package shape against an actual user export.

## Compatibility and rollback

The ChatGPT provider and its archive remain unchanged. Removing `gpt_exporter/providers/discord` restores the previous single-provider behavior; the provider-neutral core does not depend on Discord. No archive migration or data rewrite is required to roll back this first Discord integration.
