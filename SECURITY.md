# Security

## Sensitive archive data

gpt-exporter processes private ChatGPT conversation data and may temporarily handle authenticated browser-session data while the collector runs inside ChatGPT.

Never publish or attach the following to an issue or pull request:

- `chatgpt-archive-source.json`;
- archived conversation JSON/XZ files;
- downloaded assets or private attachments;
- SQLite indexes built from an archive;
- cookies, access tokens, account IDs, authorization headers, or browser-session data;
- generated DOCX or Markdown containing private conversations unless deliberately sanitized.

When reporting a bug, prefer a minimal synthetic reproduction.

## Reporting a security issue

Please do not open a public issue for a vulnerability that could expose credentials, authentication material, or private archive contents. Contact the repository owner privately through an appropriate GitHub contact channel instead.

## Supported version

The current development line is based on gpt-exporter v2.7. Security fixes are expected to target the current `main` branch.
