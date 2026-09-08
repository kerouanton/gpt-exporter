# Provider selection

The desktop launcher now has an application-level provider-selection boundary.

## Layers

```text
gpt_exporter_gui.py
        |
        v
gpt_exporter.application
        |
        +--> ProviderRegistry (provider-neutral core)
        +--> provider selector (provider-neutral Tk UI)
        |
        v
selected provider application
        |
        +--> providers/gpt/ui/app.py   (currently installed)
        +--> providers/<future>/...    (future providers)
```

`ProviderRegistry` belongs to `gpt_exporter.core` and imports no concrete provider. Concrete providers are registered only by application composition code.

The selector consumes `ProviderDescriptor` values only. It contains no ChatGPT-specific labels, archive paths, schema handling, collector workflow, or provider imports.

## Current provider

The first registered desktop provider is:

```text
provider_id  : gpt
display_name : ChatGPT
version      : 1
```

Selecting ChatGPT launches the existing provider-owned GUI unchanged.

For automation and compatibility the provider can also be selected directly:

```powershell
py .\gpt_exporter_gui.py --provider gpt
```

Provider-specific arguments that are not consumed by the selector are forwarded to the selected provider application.

## Architectural invariant

Adding provider selection does not weaken the existing provider-removal rule. `gpt_exporter.core`, including `ProviderRegistry`, must still import and operate with `providers/gpt` physically absent. The application composition layer may register whichever concrete providers are installed; the shared engine never imports one as a prerequisite.
