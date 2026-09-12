# MSNE rename inventory

This document is the phase-1 inventory for issue #86: the controlled rename from **GPT Exporter** to **Multi Social Network Explorer (MSNE)**.

The rename is intentionally split by compatibility surface. A product rename must not implicitly rename the Python import namespace, provider SDK, distribution metadata, repository, persistent data paths, Windows executable, or provider entry-point group.

## Identity surfaces

| Surface | Current value | Phase-1 decision |
| --- | --- | --- |
| Visible product name | `GPT Exporter` | Keep unchanged in the identity-foundation PR; later switch to `Multi Social Network Explorer`. |
| Short product name | none | Introduce canonical short name `MSNE`. |
| Python distribution | `gpt-exporter` | Treat as legacy compatibility identity until a deliberate distribution migration is designed. |
| Python import package | `gpt_exporter` | Keep stable during the visible rename. Existing providers import `gpt_exporter.provider_sdk`. |
| Provider entry-point group | `gpt_exporter.provider_plugins` | Keep stable during the visible rename; this is an external provider contract. |
| GitHub repository | `kerouanton/gpt-exporter` | Rename last, after code/release/documentation compatibility is complete. |
| Windows onedir directory/executable | `GPT Exporter/GPT Exporter.exe` | Migrate in a dedicated packaging PR with explicit legacy-launcher policy. |
| Windows CI artifact | `GPT-Exporter-Windows-onedir` | Migrate with packaging, not with the first visible-name change. |
| Default ChatGPT archive directory | `~/Documents/ChatGPT Archive` | Provider data identity, not host product identity; do not rename as part of MSNE. |

## Current central identity source

`gpt_exporter/version.py` already owns the visible application name, version, license and repository URL. Phase 1 extends it with explicit legacy/current/target identity constants without changing behavior.

The important distinction is:

```text
legacy product name        GPT Exporter
future visible product     Multi Social Network Explorer
short product name         MSNE
legacy distribution        gpt-exporter
legacy import namespace    gpt_exporter
legacy repository name     gpt-exporter
```

The legacy technical names remain valid compatibility surfaces even after `APP_NAME` changes in a later PR.

## Provider compatibility

The provider milestone established independently packaged providers that depend on the host SDK. Existing provider packages currently use:

```text
gpt_exporter.provider_sdk
gpt_exporter.provider_plugins
gpt-exporter>=2.9.0
```

Those names must not be changed as a side effect of the visible product rename. Any future SDK/distribution rename requires its own versioned compatibility plan.

## Windows packaging compatibility

The current Windows build derives version-resource `ProductName`, `FileDescription`, and `OriginalFilename` from `APP_NAME`, while workflow paths still explicitly reference `GPT Exporter` and the artifact name `GPT-Exporter-Windows-onedir`.

Therefore changing `APP_NAME` alone would create a mixed package: new PE metadata with old filesystem/artifact names. The visible rename and Windows executable migration must be coordinated deliberately in a later phase.

## Persistent data policy

Provider-owned archive locations such as `ChatGPT Archive` describe the source/archive domain rather than the host application and should not be renamed automatically.

Before changing any host-owned persistent path, locate and classify workspace catalogs, settings, caches, databases and release/install state. Existing installations must remain discoverable without manual moves.

## Phase sequence

1. Identity foundation: explicit constants and this inventory; no visible behavior change.
2. Visible UI/help/documentation product rename to Multi Social Network Explorer / MSNE.
3. Windows executable, directory and artifact migration with compatibility tests.
4. Deliberate decision on distribution/import namespace migration; preserve `gpt_exporter.provider_sdk` compatibility.
5. Persistent host-data migration only where a host-owned old-name path actually exists.
6. GitHub repository rename last.

## Non-goals of phase 1

- no Python package rename;
- no distribution rename;
- no repository rename;
- no provider entry-point group rename;
- no archive/workspace relocation;
- no Windows executable rename;
- no visible product-name change yet.
