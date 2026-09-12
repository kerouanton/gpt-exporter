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

Durable activation state is stored per-user in `providers.json` beside the established workspace settings under the historical application-data directory. Disabling a provider does not delete its package or any archive data. Changes take full effect on the next MSNE start.

Zero active providers is valid. In that state MSNE starts in a provider-neutral recovery window instead of trying to resolve a conversation workspace. The recovery UI keeps `Providers...` reachable so an installed provider can be re-enabled; after re-enabling, restart MSNE to resume the normal workspace shell.

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

Implemented so far:

- durable enable/disable state;
- application startup honors disabled providers;
- the Providers dialog exposes `Enable` / `Disable` controls;
- all providers may be disabled;
- zero-provider startup enters a recovery/management shell rather than failing;
- provider packages and archive data are untouched by activation changes;
- isolated per-user provider directory under the established application-data root;
- `Install from file...` for `.whl` provider artifacts;
- pre-install validation of wheel structure, provider entry-point metadata and archive paths;
- SHA-256 display and explicit confirmation before executable provider code is installed;
- staged extraction and atomic replacement of a previously managed version;
- managed provider roots are added to discovery without mutating global Python or PyInstaller `_internal` files.

Managed wheels are stored one distribution per directory below the per-user provider root. Reinstalling the same distribution replaces the previously managed copy atomically. MSNE refreshes its inventory after installation, but a restart is required before relying on a newly installed/replaced provider for an active workspace because Python modules may already be loaded in the current process.

Still planned for Stage C:

- remove locally managed provider artifacts;
- stronger runtime activation validation with rollback when a newly installed provider cannot load;
- explicit managed/bundled provenance in the ProviderManager record/UI;
- dependency policy for third-party wheels that require additional Python distributions.

The GUI must not perform `git clone`. End-user installation targets the isolated per-user provider location rather than the global Python environment or PyInstaller's bundled `_internal` tree.

### Stage D — catalog and updates

Planned:

- signed or otherwise authenticated catalog metadata hosted independently of the executable;
- Available / Installed / Update available views;
- artifact URL, SHA-256 and compatibility metadata;
- explicit user action before install/update.

### Stage E — repository separation

Only after the provider contract and install/update path are stable should the current ChatGPT and Discord provider packages move to separate development repositories. Developer workflow can then be a normal clone plus `pip install -e .`, while end users consume provider artifacts rather than Git repositories.

## Trust and safety boundary

Installing a provider is equivalent to installing executable Python code. Therefore install/update operations display the provider distribution identity, version, declared provider entry points, destination and SHA-256 before confirmation. The installer rejects path traversal and symbolic-link members and does not invoke `pip`, Git, or a global package manager. Future catalog installs must additionally verify trusted catalog integrity metadata and reject incompatible provider APIs before activation.
