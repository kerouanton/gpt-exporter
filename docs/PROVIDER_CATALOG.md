# Provider catalog

Stage D introduces a catalog metadata contract independently from catalog transport and installation. The first increment is deliberately read-only: it validates catalog identity and provider metadata, compares semantic `MAJOR.MINOR.PATCH` versions, and exposes enough trusted artifact identity for the later download/install path.

## Schema version 1

A catalog document is a JSON object with:

- `schema_version`: currently `1`;
- `catalog_id`: stable catalog identity;
- `generated_at`: catalog generation timestamp;
- `providers`: a list containing the latest advertised release of each provider.

Each provider entry contains:

- `provider_id`: stable descriptor ID used by MSNE;
- `display_name`;
- `distribution_name`: Python distribution identity;
- `version`: strict `MAJOR.MINOR.PATCH` release version;
- `provider_api_version`;
- `min_msne_version`: strict `MAJOR.MINOR.PATCH` minimum host version;
- `artifact_url`: HTTPS wheel URL;
- `sha256`: lowercase SHA-256 of the exact wheel bytes;
- optional `capabilities` and `description`.

The parser rejects duplicate provider IDs, duplicate normalized distribution names, non-HTTPS artifact URLs, malformed hashes, unsupported schema versions, and malformed version strings. Catalog parsing never downloads or executes provider code.

`catalog/provider-catalog.sample.json` is a development fixture demonstrating ChatGPT and Discord metadata. Its `example.invalid` URLs and placeholder hashes are intentionally non-installable.

## Trust boundary

Artifact SHA-256 is necessary but does not authenticate the catalog itself. This increment therefore does **not** enable catalog downloads or installs. A following Stage D increment must authenticate catalog metadata (for example with a pinned public signing key) before catalog-originated artifact URLs are trusted. Once the catalog itself is authenticated, downloaded wheel bytes must match the catalog SHA-256 before the existing Stage C wheel inspection, dependency policy, runtime validation and rollback pipeline is invoked.

## Planned UI/transport steps

The remaining Stage D work is intentionally layered:

1. authenticated catalog transport and durable cached snapshot;
2. ProviderManager `Available / Installed / Update available` presentation;
3. explicit catalog download with SHA-256 verification;
4. reuse of the existing validated install/update/rollback pipeline;
5. update checks without background mutation or automatic installation.

No Stage D operation should run Git, invoke global `pip`, overwrite PyInstaller `_internal`, or install executable code without an explicit user confirmation.
