# Contributing to gpt-exporter

Thanks for your interest in gpt-exporter.

## Development principles

The local archive is cumulative and conservative. Canonical durable data is provider source/canonical conversation data plus preserved assets; DOCX, Markdown, indexes, manifests and reports are derived and rebuildable unless a provider document explicitly states otherwise.

Changes must not silently delete, prune, normalize, replace, or reinterpret canonical archive data. Ambiguous asset mappings must remain unresolved rather than being guessed.

## Provider boundary

The project is evolving toward independently packageable providers. New development must preserve one-way dependency:

```text
provider implementation ---> shared core/SDK
shared core/application -X-> concrete provider implementation
```

Do not add a new service by scattering `if provider_id == ...` branches through the Browser, shared workflow, shared renderer or application shell.

Shared UI/workflow facilities belong outside providers. Providers expose source-specific capabilities, data, resources and policy; they do not get a separate duplicate application experience simply because the source differs.

Important operations must not exist only inside Tkinter callbacks. GUI and CLI/library callers must invoke the same underlying provider/shared business operations.

See `docs/PROVIDER_PACKAGE_ARCHITECTURE.md` before adding a provider or changing application composition.

## Development setup

Use Python 3.12 or newer.

```text
python -m pip install -r requirements.txt
```

Before submitting a change, compile all Python sources and run tests relevant to the modified code. For provider-contract work, include physical provider removal/addition tests where applicable, not only import-level unit tests.

## Pull requests

Keep changes focused. Describe behavioral changes, archive-format implications, provider-boundary implications, and migration or rollback requirements where applicable.

Changes affecting canonical data, cumulative behavior, deletion policy, history-completeness semantics, visible-message semantics, asset-link semantics, provider discovery/contracts, or shared UI ownership require explicit documentation.

Do not weaken current conservative preservation/deletion behavior merely to satisfy a stale test expectation; reconcile the test with the intended documented behavior.

Do not commit personal ChatGPT/Discord archives, browser exports, SQLite indexes, generated conversation exports, downloaded assets, credentials, cookies, access tokens, account IDs, or local IDE state.

## Future provider repositories

The planned provider-package architecture should allow packages such as `export-provider-linkedin` to be developed in independent repositories against a stable provider API/SDK. Until that contract is implemented, avoid designing new providers around direct imports from `gpt_exporter.application` or shared Tkinter internals.

## License

By contributing, you agree that your contribution is licensed under GPL-3.0-or-later, the same license as the project.
