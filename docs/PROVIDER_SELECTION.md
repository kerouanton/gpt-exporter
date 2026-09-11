# Provider selection and workspace composition

GPT Exporter now operates with named provider workspaces and a shared Browser/application shell. ChatGPT and Discord are both implemented providers.

This document describes the **current** composition boundary. The stronger next milestone—dynamic, independently installable provider packages—is specified in `PROVIDER_PACKAGE_ARCHITECTURE.md`.

## Current layers

```text
gpt_exporter_gui.py
        |
        v
gpt_exporter.application
        |
        +--> ProviderRegistry
        +--> WorkspaceCatalog
        +--> shared Browser/workspace shell
        |
        v
provider capabilities/actions
        |
        +--> providers/gpt
        +--> providers/discord
```

`ProviderRegistry` belongs to `gpt_exporter.core` and imports no concrete provider. The Browser and shared archive workflow consume provider-neutral workspace/action contracts rather than ChatGPT schemas.

## Current providers

Installed provider implementations currently include:

```text
provider_id  : gpt
display_name : ChatGPT

provider_id  : discord
display_name : Discord
```

The application remembers a named active workspace. Shared Browser behavior operates against that workspace's SQLite archive/index rather than launching a fundamentally different Browser for each service.

Legacy explicit provider launch paths remain reachable during migration, but they are compatibility paths rather than the desired long-term architecture.

## CLI relationship

Provider/application behavior must not depend on Tkinter. The shared GUI is a client of underlying application/provider operations, and command-line/library callers must be able to invoke the same business logic.

The historical explicit provider option remains available during transition:

```powershell
py .\gpt_exporter_gui.py --provider gpt
py .\gpt_exporter_gui.py --provider discord
```

This mechanism is not the future provider-package API; it is a compatibility path while shared composition is consolidated.

## Current limitation

`gpt_exporter.application` still explicitly names the known providers when it:

- imports/registers provider classes;
- proposes default workspaces;
- constructs compatibility launchers;
- translates legacy provider-specific arguments;
- constructs provider-specific workspace action objects.

Therefore the project is **provider-neutral in important shared layers, but not yet provider-packageable**.

A new provider still requires edits to central application composition. That is exactly what the next milestone must remove.

## Target selection/discovery model

The target is:

```text
start application
      |
      v
discover installed provider packages
      |
      v
validate provider API compatibility
      |
      v
register descriptors + capabilities + workspace proposals
      |
      v
same shared GUI and CLI surfaces
```

Adding or removing a provider package must not require an edit to `application.py`, the Browser, the shared archive workflow, or central CLI dispatch.

The application must also tolerate zero installed providers without import failure.

## Architectural invariant

Provider discovery must preserve one-way dependency:

```text
provider package ---> shared core/SDK
shared core      -X-> concrete provider package
```

The final acceptance tests must physically remove ChatGPT and Discord independently, remove all providers, and add a synthetic third provider that was never named in main-application source code.

See `PROVIDER_PACKAGE_ARCHITECTURE.md` and `HANDOVER_PROVIDER_PACKAGING.md` for the complete next-milestone definition.
