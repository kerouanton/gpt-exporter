# Documentation

Current architecture and development documents:

- `ARCHITECTURE.md` — current provider-neutral architecture, shared/provider ownership boundaries, Discord multipart state, and future direction.
- `DISCORD_PROVIDER.md` — current Discord collector, archive, cumulative history, multipart DOCX, participant header, regeneration, and remote-deletion behavior.
- `PROVIDER_SELECTION.md` — current shared workspace/provider composition and the remaining explicit application coupling.
- `PROVIDER_PACKAGE_ARCHITECTURE.md` — **next milestone specification** for dynamically discovered, independently packageable providers with one shared GUI/CLI workflow model.
- `HANDOVER_PROVIDER_PACKAGING.md` — detailed 2026-09-10 handover for continuing the provider-packaging/MSNE preparation work in a new development conversation.
- `TODO.md` — intentionally deferred work, including Browser multipart navigation and changed-period-only DOCX regeneration.
- `SHARED_ASSET_REFACTOR_PLAN.md` — historical shared-asset refactor planning record.
- `PORTABILITY_NOTES.md` — path/platform portability notes.

Historical release/workflow documents:

- `V2_8_GUI_WORKFLOW.md` — v2.8 GUI-first archive workflow design and implementation notes.
- `RELEASE_NOTES_V2.8.md` — v2.8 release summary and validation record.
- `RELEASE_NOTES_V2.9.md` — v2.9 Windows `onedir` distribution and reusable-package release summary.
- `PUBLIC_RELEASE_CHECKLIST.md` — historical checklist used for the first public-release preparation.

Repository-level documents:

- `README.md` — public project overview and current multi-provider direction.
- `CHANGELOG.md` — detailed release lineage plus current unreleased consolidation notes.
- `FROZEN_VERSION.md` — historical v2.7 ChatGPT preservation baseline.
- `SECURITY.md` — privacy and security reporting guidance.
- `CONTRIBUTING.md` — contribution, preservation, and provider-boundary rules.

## Next architectural milestone

The immediate architectural goal is stronger than keeping ChatGPT and Discord in separate directories. Providers must become independently installable/discoverable packages so that adding or removing a provider requires no main-application source change.

The shared Browser, archive workflow, processing/progress UI, indexing, rendering, workspace model, and CLI/application lifecycle remain outside providers. Providers supply source-specific capabilities and data, not a different UI/application.

After that boundary is fully implemented and validated, the planned future project identity is **Multi Social Network Explorer (MSNE)**. The rename is intentionally deferred until provider independence is real.
