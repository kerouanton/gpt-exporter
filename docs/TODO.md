# TODO

This file records deliberately deferred work. Items here are not release blockers unless explicitly promoted into a milestone.

## Discord multipart DOCX follow-ups

The density-based multipart DOCX implementation is working and has been validated on the 6,674-message Gadget MCS ↔ Littleloulita DM. The canonical/raw conversation remains a single logical archive; multipart DOCX files are derived views.

Deferred improvements:

- **Browser multipart navigation:** the Browser currently stores/opens one `docx_path`, intentionally the most recent part. Later, expose all DOCX parts for one logical conversation without creating duplicate Browser conversation rows. A part picker/history surface is preferable to treating parts as independent conversations.
- **Incremental multipart regeneration:** when only the current period changes, avoid rebuilding historical DOCX parts that are already current. The first multipart conversion must still build all required parts. Correctness takes precedence over optimization.
- **Result/progress reporting:** provider workflow status currently emphasizes the primary/latest DOCX path. Later, display or log all generated multipart paths consistently where useful.
- **Resolver cleanup:** review provider path-resolution helpers that still assume a single unsuffixed DOCX and make them multipart-aware only where the shared Browser/workflow actually requires it.

Do **not** add a `Regenerate All DOCX…` command. Manual deletion plus `Regenerate Missing DOCX…` is the accepted recovery/test workflow.

## Provider packaging milestone

The next major architectural project is defined in `PROVIDER_PACKAGE_ARCHITECTURE.md` and handed over in `HANDOVER_PROVIDER_PACKAGING.md`.

Primary tasks include dynamic provider discovery, removal of concrete-provider conditionals/imports from the main application, a stable capability/compatibility contract, shared GUI/CLI dispatch, Windows packaged-provider discovery, and tests proving physical provider removal/addition.

## Future product rename

After provider packaging and independence are proven, prepare a separate controlled rename from GPT Exporter / `gpt-exporter` to **Multi Social Network Explorer (MSNE)**. Do not mix that rename into the provider-contract refactor.
