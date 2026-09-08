"""Top-level application composition for named conversation workspaces."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.ui.provider_selector import choose_provider
from gpt_exporter.ui.workspace_selector import choose_workspace
from gpt_exporter.version import APP_NAME, display_version
from gpt_exporter.workspaces import ConversationWorkspace, WorkspaceCatalog

ProviderLauncher = Callable[[list[str]], int]


def _provider_package_missing(error: ModuleNotFoundError, package: str) -> bool:
    return bool(error.name and (error.name == package or error.name.startswith(package + ".")))


def build_provider_registry() -> ProviderRegistry:
    """Register concrete providers at the application boundary.

    Concrete imports live here rather than in ``gpt_exporter.core`` so the core
    remains usable when any provider package is absent.
    """
    registry = ProviderRegistry()

    try:
        from gpt_exporter.providers.gpt.provider import ChatGPTProvider
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.gpt"):
            raise
    else:
        registry.register(ChatGPTProvider())

    try:
        from gpt_exporter.providers.discord.provider import DiscordProvider
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.discord"):
            raise
    else:
        registry.register(DiscordProvider())

    return registry


def build_default_workspaces(registry: ProviderRegistry) -> tuple[ConversationWorkspace, ...]:
    """Compose provider-owned defaults into provider-neutral named workspaces."""
    provider_ids = set(registry.provider_ids())
    workspaces: list[ConversationWorkspace] = []

    if "gpt" in provider_ids:
        from gpt_exporter.providers.gpt.paths import default_archive_paths

        workspaces.append(
            ConversationWorkspace(
                name="ChatGPT",
                provider_id="gpt",
                root_path=default_archive_paths().root,
                description="Default ChatGPT conversation archive.",
            )
        )

    if "discord" in provider_ids:
        from gpt_exporter.providers.discord.archive import default_archive_root

        workspaces.append(
            ConversationWorkspace(
                name="Discord",
                provider_id="discord",
                root_path=default_archive_root(),
                description="Default Discord conversation archive.",
            )
        )

    return tuple(workspaces)


def build_workspace_catalog(
    registry: ProviderRegistry,
    *,
    path: Path | str | None = None,
) -> WorkspaceCatalog:
    """Open the durable catalog and seed installed-provider defaults once."""
    catalog = WorkspaceCatalog(path)
    catalog.seed(build_default_workspaces(registry))
    return catalog


def _run_provider_main(provider_main: Callable[[], int], arguments: list[str]) -> int:
    previous = sys.argv
    try:
        sys.argv = [previous[0], *arguments]
        return int(provider_main())
    finally:
        sys.argv = previous


def _launch_gpt(arguments: list[str]) -> int:
    from gpt_exporter.providers.gpt.ui import app as provider_app

    return _run_provider_main(provider_app.main, arguments)


def _launch_discord(arguments: list[str]) -> int:
    from gpt_exporter.providers.discord.ui import app as provider_app

    return _run_provider_main(provider_app.main, arguments)


def build_provider_launchers() -> dict[str, ProviderLauncher]:
    """Return lazy launchers for provider UIs installed with this application."""
    launchers: dict[str, ProviderLauncher] = {}

    try:
        from gpt_exporter.providers.gpt import provider as _gpt_provider  # noqa: F401
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.gpt"):
            raise
    else:
        launchers["gpt"] = _launch_gpt

    try:
        from gpt_exporter.providers.discord import provider as _discord_provider  # noqa: F401
    except ModuleNotFoundError as error:
        if not _provider_package_missing(error, "gpt_exporter.providers.discord"):
            raise
    else:
        launchers["discord"] = _launch_discord

    return launchers


def workspace_provider_arguments(workspace: ConversationWorkspace) -> list[str]:
    """Translate a provider-neutral workspace into provider-owned CLI inputs."""
    if workspace.provider_id == "gpt":
        return ["--database", str(workspace.database_path)]
    if workspace.provider_id == "discord":
        return ["--archive-root", str(workspace.root_path)]
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Choose and launch a named conversation workspace"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {display_version()}",
        help="Show the application version and exit.",
    )
    parser.add_argument(
        "--workspace",
        help="Launch a named workspace directly instead of showing the selector.",
    )
    parser.add_argument(
        "--workspace-catalog",
        type=Path,
        help="Use an alternate workspace catalog JSON file.",
    )
    parser.add_argument(
        "--provider",
        help="Compatibility option: launch a provider directly by provider id.",
    )
    return parser


def _workspace_for_provider(
    catalog: WorkspaceCatalog,
    provider_id: str,
) -> ConversationWorkspace | None:
    active = catalog.get_active()
    if active is not None and active.provider_id == provider_id:
        return active
    return next(
        (
            workspace
            for workspace in catalog.list(enabled_only=True)
            if workspace.provider_id == provider_id
        ),
        None,
    )


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    arguments, provider_arguments = build_parser().parse_known_args(raw_arguments)
    registry = build_provider_registry()
    launchers = build_provider_launchers()

    available_provider_ids = {
        descriptor.provider_id
        for descriptor in registry.descriptors()
        if descriptor.provider_id in launchers
    }
    if not available_provider_ids:
        raise RuntimeError("No conversation providers with a GUI are installed.")

    catalog = build_workspace_catalog(registry, path=arguments.workspace_catalog)
    workspace: ConversationWorkspace | None = None

    if arguments.workspace:
        workspace = catalog.get(arguments.workspace)
        if not workspace.enabled:
            raise ValueError(f"Workspace '{workspace.name}' is disabled")
        if workspace.provider_id not in available_provider_ids:
            raise ValueError(
                f"Workspace '{workspace.name}' uses unavailable provider: {workspace.provider_id}"
            )
    elif arguments.provider:
        provider_id = arguments.provider
        if provider_id not in available_provider_ids:
            raise ValueError(f"Unknown or unavailable provider: {provider_id}")
        workspace = _workspace_for_provider(catalog, provider_id)
        if workspace is None:
            # Preserve the old direct-provider behavior if a future provider has
            # no seeded/default workspace yet.
            return int(launchers[provider_id](provider_arguments))
    else:
        workspaces = tuple(
            workspace
            for workspace in catalog.list(enabled_only=True)
            if workspace.provider_id in available_provider_ids
        )
        selected_name = choose_workspace(
            workspaces,
            default_workspace_name=(catalog.get_active_name() or "ChatGPT"),
        )
        if selected_name is None:
            return 0
        workspace = catalog.get(selected_name)

    catalog.set_active(workspace.name)
    launch_arguments = [*workspace_provider_arguments(workspace), *provider_arguments]
    return int(launchers[workspace.provider_id](launch_arguments))


if __name__ == "__main__":
    raise SystemExit(main())
