# Provider catalog

Stage D introduces a catalog metadata contract independently from provider installation. The current implementation validates catalog identity and provider metadata, compares semantic `MAJOR.MINOR.PATCH` versions, supports origin-pinned HTTPS retrieval, and keeps a durable per-user cache of the last validated snapshot.

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

## HTTPS transport and cache

`provider_catalog_transport.py` adds a deliberately narrow network boundary:

- the requested catalog URL must use HTTPS;
- callers must supply one or more pinned allowed hostnames;
- redirects are accepted only when the final HTTPS URL remains on an allowed hostname;
- response size is bounded before UTF-8 decoding or JSON parsing;
- only schema-valid catalog snapshots are written to the per-user cache;
- a malformed cached snapshot is ignored rather than trusted;
- cache replacement is performed through a temporary file and atomic rename.

The default cache lives beside the existing per-user provider state under the historical application-data root, in `catalog/provider-catalog.json`.

This transport authenticates the HTTPS origin and prevents silent redirect to an untrusted host. It does **not** yet provide publisher-level cryptographic signing of the catalog. A later hardening step may add a pinned public signing key without changing the schema consumed by the rest of ProviderManager.

## Trust boundary

Artifact SHA-256 is necessary but does not by itself authenticate catalog metadata. Catalog-originated provider installation therefore remains disabled in this increment. Once the UI/install path is enabled, downloaded wheel bytes must match the catalog SHA-256 before the existing Stage C wheel inspection, dependency policy, runtime validation and rollback pipeline is invoked.

## Remaining Stage D work

The remaining work is intentionally layered:

1. wire the cached catalog into ProviderManager as `Available / Installed / Update available` state;
2. add explicit catalog refresh in the Providers UI using a fixed trusted source configuration;
3. add provider wheel download with SHA-256 verification;
4. reuse the existing validated install/update/rollback pipeline;
5. optionally add catalog signature verification with a pinned public key;
6. support update checks without background mutation or automatic installation.

No Stage D operation should run Git, invoke global `pip`, overwrite PyInstaller `_internal`, or install executable code without an explicit user confirmation.
