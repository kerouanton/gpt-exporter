# ProviderManager

MSNE providers are independently packaged Python distributions discovered through the stable `gpt_exporter.provider_plugins` entry-point group. `ProviderManager` is the host-side layer that turns low-level discovery into explicit provider lifecycle state and controlled installation/update/removal operations.

## Goals

- Keep the shared application provider-neutral.
- Preserve the current provider entry-point contract while the MSNE rename is still in progress.
- Make broken or incompatible providers visible without preventing MSNE from starting.
- Keep provider installation out of the GUI's direct package/import logic.
- Support source development (`pip install -e .`) independently from end-user artifact installation.
- Make Windows onedir provider installation possible without requiring Git.

## State model

The current implementation exposes these runtime states:

- `enabled`: provider loaded successfully and is available to the application;
- `disabled`: provider is installed/discovered but excluded from application composition by durable user preference;
- `incompatible`: an installed/discovered provider advertises an unsupported provider API version;
- `broken`: a provider candidate exists but could not be imported, constructed, or validated.

`installed` and `discovered` remain explicit record attributes so later catalog/install transitions do not require redesigning the UI model.

Durable activation state is stored per-user in `providers.json` beside the established workspace settings under the historical application-data directory. Disabling a provider does not delete its package or any archive data. Changes take full effect on the next MSNE start. The UI prevents disabling the final healthy provider so the management dialog remains reachable on the next launch.

## Provider metadata

The current provider descriptor supplies:

- `provider_id`
- `display_name`
- `version`
- `api_version`
- `capabilities`

A later compatibility stage will add an explicit minimum-MSNE-version constraint. API compatibility remains mandatory: an incompatible provider must be disabled cleanly rather than causing an application traceback. Discovery retains descriptor metadata for incompatible providers so the management UI can show the advertised API/version even though activation is rejected.

## Delivery stages

### Stage A/B — read-only inventory

Implemented:

- central `ProviderManager` snapshot;
- successful, incompatible and broken provider records;
- `Tools -> Providers...` GUI;
- refresh and diagnostic details;
- no mutation of the Python environment.

### Stage C — local lifecycle and artifact management

First Stage C increment implemented:

- durable enable/disable state;
- application startup honors disabled providers;
- the Providers dialog exposes `Enable` / `Disable` controls;
- the final healthy provider cannot be disabled;
- provider packages and archive data are untouched by activation changes.

Still planned for Stage C:

- app-local provider directory for the Windows onedir distribution;
- `Install from file...` for a provider wheel/package artifact;
- remove locally installed provider artifacts;
- integrity validation before installation;
- safe rollback when activation fails.

The GUI must not perform `git clone`. End-user installation must target an isolated app-local/per-user provider location rather than the global Python environment or PyInstaller's bundled `_internal` tree.

### Stage D — catalog and updates

Planned:

- signed or otherwise authenticated catalog metadata hosted independently of the executable;
- Available / Installed / Update available views;
- artifact URL, SHA-256 and compatibility metadata;
- explicit user action before install/update.

### Stage E — repository separation

Only after the provider contract and install/update path are stable should the current ChatGPT and Discord provider packages move to separate development repositories. Developer workflow can then be a normal clone plus `pip install -e .`, while end users consume provider artifacts rather than Git repositories.

## Trust and safety boundary

Installing a provider is equivalent to installing executable Python code. Therefore install/update operations must display the provider identity and source, verify integrity metadata, reject incompatible provider APIs before activation, and never silently replace a working provider with an unverified artifact.
