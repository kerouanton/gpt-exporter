# export-provider-chatgpt

Independent ChatGPT provider distribution for GPT Exporter and the future Multi Social Network Explorer (MSNE).

The package depends on the shared `gpt-exporter` provider SDK/application surface and registers itself through the `gpt_exporter.provider_plugins` entry-point group. The host application must not import this package by name.

During the monorepo migration the historical `gpt_exporter.providers.gpt` implementation remains temporarily available for compatibility tests. This package is the extraction target and is expected to become independently versioned/released once parity and removal tests are green.
