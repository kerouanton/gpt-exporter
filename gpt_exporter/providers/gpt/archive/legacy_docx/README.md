# Archived ChatGPT legacy DOCX migration

This namespace is reserved for the completed historical DOCX -> normalized JSON migration.

It is deliberately inside the ChatGPT provider because the migration is not a core engine capability and must not constrain future providers such as Discord.

The active legacy implementation is not moved here yet because the current SQLite rebuild path still verifies and imports against the historical DOCX files. The cutover is complete only when the normalized JSON can rebuild the archive independently of those DOCX sources.

After that cutover:

- DOCX parsing, Word IR, role inference, reconstruction and semantic-audit code belongs here as archived migration material (or may later be removed under repository-retention policy);
- the provider-neutral core must contain no `legacy_docx` concepts;
- normal ChatGPT operation must use only the provider's canonical JSON/archive path;
- deleting this archive namespace must not affect normal runtime behavior.
