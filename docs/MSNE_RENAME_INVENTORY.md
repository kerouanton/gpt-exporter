# MSNE rename inventory

This document tracks issue #86: the controlled rename from **GPT Exporter** to **Multi Social Network Explorer (MSNE)**.

The rename is intentionally split by compatibility surface. A product rename must not implicitly rename the Python import namespace, provider SDK, distribution metadata, repository, persistent data paths, Windows executable, or provider entry-point group.

## Identity surfaces

| Surface | Current value | Migration state |
| --- | --- | --- |
| Visible product name | `Multi Social Network Explorer` | Migrated in phase 2. |
| Short product name | `MSNE` | Canonical short name. |
| Python distribution | `gpt-exporter` | Legacy compatibility identity; unchanged pending an explicit distribution decision. |
| Python import package | `gpt_exporter` | Stable compatibility surface. Existing providers import `gpt_exporter.provider_sdk`. |
| Provider entry-point group | `gpt_exporter.provider_plugins` | Stable external provider contract. |
| GitHub repository | `kerouanton/gpt-exporter` | Rename last, after code/release/documentation compatibility is complete. |
| Canonical Windows executable | `MSNE.exe` | Phase 3 canonical executable. |
| Legacy Windows executable | `GPT Exporter.exe` | Retained in the same onedir as a compatibility launcher during migration. |
| Windows onedir directory | `GPT Exporter` | Deliberately retained for this phase to preserve existing filesystem paths/shortcuts. |
| Windows CI artifact | `MSNE-Windows-onedir` | Migrated in phase 3. |
| Future Windows release ZIP | `MSNE-<version>-Windows-x64.zip` | Migrated in phase 3. |
| Default ChatGPT archive directory | `~/Documents/ChatGPT Archive` | Provider data identity, not host product identity; do not rename as part of MSNE. |

## Central identity source

`gpt_exporter/version.py` owns the product and migration identities. The important distinction is now:

```text
visible product             Multi Social Network Explorer
short product name          MSNE
canonical Windows basename  MSNE
legacy Windows basename     GPT Exporter
current onedir folder       GPT Exporter
legacy distribution         gpt-exporter
legacy import namespace     gpt_exporter
legacy repository name      gpt-exporter
```

The legacy technical names remain valid compatibility surfaces even though the visible product identity is now MSNE.

## Provider compatibility

The provider milestone established independently packaged providers that depend on the host SDK. Existing provider packages currently use:

```text
gpt_exporter.provider_sdk
gpt_exporter.provider_plugins
gpt-exporter>=2.9.0
```

Those names are not changed by the visible product or Windows executable rename. Any future SDK/distribution rename requires its own versioned compatibility plan.

## Windows packaging compatibility

Phase 2 moved PE product metadata to `Multi Social Network Explorer` while retaining the historical physical executable name.

Phase 3 introduces **two executables in one onedir**:

```text
GPT Exporter\MSNE.exe
GPT Exporter\GPT Exporter.exe
```

`MSNE.exe` is canonical. `GPT Exporter.exe` remains a compatibility launcher that runs the same application code and carries the same MSNE product metadata, but its PE `OriginalFilename` remains `GPT Exporter.exe`.

The outer `GPT Exporter` directory deliberately remains unchanged in this phase. This avoids breaking existing extracted-directory paths, shortcuts, scripts or upgrade overlays merely to establish the new executable identity. Folder migration can be evaluated separately once the canonical executable has shipped successfully.

The CI artifact name becomes `MSNE-Windows-onedir`. Future new-version release archives use `MSNE-<version>-Windows-x64.zip`, even though the archive still contains the compatibility-preserving `GPT Exporter` outer directory for now.

## Release safety

A change to `gpt_exporter/version.py` triggers the Windows release workflow. The workflow first checks whether the final release tag already exists:

- HTTP 200: the release exists, so the workflow succeeds as a no-op;
- HTTP 404: a new final release may proceed;
- any other response: fail immediately rather than treating an API/auth/network error as a missing release.

This allows identity metadata to evolve without attempting to republish an existing final version such as `v2.9.0`.

## Persistent data policy

Provider-owned archive locations such as `ChatGPT Archive` and `Discord Archive` describe the source/archive domain rather than the host application and are not renamed automatically.

Before changing any host-owned persistent path, locate and classify workspace catalogs, settings, caches, databases and release/install state. Existing installations must remain discoverable without manual moves.

## Phase sequence

1. **Completed:** identity foundation and explicit compatibility constants.
2. **Completed:** visible UI/help/documentation product rename to Multi Social Network Explorer / MSNE.
3. **Current:** canonical `MSNE.exe`, legacy `GPT Exporter.exe`, MSNE artifact/release archive naming, historical onedir folder retained.
4. Deliberate decision on distribution/import namespace migration; preserve `gpt_exporter.provider_sdk` compatibility.
5. Persistent host-data migration only where a host-owned old-name path actually exists.
6. GitHub repository rename last.

## Deliberately unchanged in phase 3

- Python package namespace `gpt_exporter`;
- distribution name `gpt-exporter`;
- provider entry-point group `gpt_exporter.provider_plugins`;
- provider SDK import path `gpt_exporter.provider_sdk`;
- GitHub repository name;
- provider archive/workspace directories;
- outer Windows onedir directory `GPT Exporter`.
