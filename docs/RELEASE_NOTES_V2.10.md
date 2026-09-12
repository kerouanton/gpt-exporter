# Multi Social Network Explorer v2.10.0

This release freezes the provider-package separation milestone and the visible product rename to **Multi Social Network Explorer (MSNE)**.

## Highlights

- Renames the visible application identity from **GPT Exporter** to **Multi Social Network Explorer (MSNE)** while preserving compatibility-sensitive Python, distribution, repository, archive, and Windows executable names where required.
- Extracts ChatGPT and Discord into independently packaged Python provider distributions:
  - `export-provider-chatgpt`
  - `export-provider-discord`
- Discovers providers dynamically through the `gpt_exporter.provider_plugins` entry-point group instead of hard-coding concrete providers in the shared host.
- Removes the old in-host provider implementation trees and, in the final cleanup, removes the transitional `gpt_exporter.providers` compatibility namespace entirely.
- Retargets launchers, provider internals, resources, tests, and compatibility wrappers directly to the extracted provider packages.
- Keeps the shared application able to validate provider installation combinations, including zero-provider and synthetic-provider discovery scenarios.
- Updates the Windows onedir build so both extracted provider packages, resources, and entry-point metadata are bundled and discoverable at runtime.
- Keeps the historical Windows executable basename `GPT Exporter.exe` for compatibility while exposing **Multi Social Network Explorer** as the visible product name and file description.

## Validation

The provider split was validated by GitHub Actions on Python 3.12 and 3.13 and by the Windows onedir build. After the final namespace cleanup, a real local smoke test on Windows confirmed that both ChatGPT and Discord still behave as before, including provider selection, existing workspace/archive access, Browser/search behavior, and normal application startup.

## Compatibility

The following compatibility surfaces intentionally remain unchanged in v2.10.0:

- Python distribution name: `gpt-exporter`
- Python import package: `gpt_exporter`
- GitHub repository name: `gpt-exporter`
- provider entry-point group: `gpt_exporter.provider_plugins`
- historical Windows executable/folder basename: `GPT Exporter`
- existing ChatGPT and Discord archive/workspace layouts

These names can be migrated separately later without coupling product branding to storage or package compatibility.

## Known critical follow-up

A very large ChatGPT conversation can currently cause the legacy collector endpoint `/backend-api/conversation/{id}` to return a server-side timeout/HTTP 500. Current ChatGPT UI behavior indicates that the service now uses a newer progressive conversation-loading endpoint for such cases. The issue is tracked separately as **#91** and is intentionally deferred from this release so the provider-packaging milestone can be frozen independently.

## Next milestone

The next planned architectural milestone is provider management: a shared `ProviderManager`, install/enable/disable/remove/update lifecycle, compatibility checks, an application-local provider installation model for Windows, and a user-facing **Providers...** interface. Provider repositories can then move out of the monorepo without changing the shared host.
