# Portability notes

GPT Exporter remains Windows-oriented, but archive roots are derived from the user environment rather than literal developer paths.

Current default provider workspaces are:

```text
%USERPROFILE%\Documents\ChatGPT Archive
%USERPROFILE%\Documents\Discord Archive
```

Shared workspace/path code should operate from an explicit archive root. Provider-specific default locations belong to provider metadata/capabilities rather than being hard-coded into the shared Browser, index, renderer or future provider discovery layer.

This distinction becomes more important for the next provider-package milestone: an independently installed provider must be able to propose its own default workspace without requiring a central `if provider_id == ...` branch.

## Windows packaged application

The existing release line supports a PyInstaller `onedir` Windows application. The future provider distribution/discovery mechanism must therefore be validated in both environments:

```text
source checkout + Python
Windows onedir packaged application
```

A provider mechanism that works only through editable Python source paths does not satisfy the target architecture.

The exact provider distribution format is intentionally undecided. See `PROVIDER_PACKAGE_ARCHITECTURE.md` for the acceptance criteria.
