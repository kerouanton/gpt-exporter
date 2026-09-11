"""Top-level application composition for named conversation workspaces."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.version import APP_NAME, display_version
from gpt_exporter.workspaces import ConversationWorkspace, WorkspaceCatalog

ProviderLauncher = Callable[[list[str]], int]


def _provider_package_missing(error: ModuleNotFoundError, package: str) -> bool:
    return bool(error.name and (error.name == package or error.name.startswith(package + ".")))


def build_provider_registry() -> ProviderRegistry:
    """Register concrete providers only at the application composition boundary."""
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
    """Compatibility launchers for explicit legacy ``--provider`` execution."""
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
    """Translate a provider-neutral workspace into historical provider CLI inputs."""
    if workspace.provider_id == "gpt":
        return ["--database", str(workspace.database_path)]
    if workspace.provider_id == "discord":
        return ["--archive-root", str(workspace.root_path)]
    return []


def build_workspace_actions(app, workspace: ConversationWorkspace):
    """Build provider commands for the common workspace shell, lazily."""
    if workspace.provider_id == "gpt":
        from gpt_exporter.providers.gpt.ui.workspace_actions import GPTWorkspaceActions

        return GPTWorkspaceActions(app, workspace)
    if workspace.provider_id == "discord":
        from gpt_exporter.providers.discord.ui.remote_delete_actions import DiscordRemoteDeleteActions

        return DiscordRemoteDeleteActions(app, workspace)
    raise ValueError(f"No shared-shell actions are registered for provider: {workspace.provider_id}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open the shared conversation browser on the active workspace"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {display_version()}",
        help="Show the application version and exit.",
    )
    parser.add_argument(
        "--workspace",
        help="Open a named workspace instead of the remembered active workspace.",
    )
    parser.add_argument(
        "--workspace-catalog",
        type=Path,
        help="Use an alternate workspace catalog JSON file.",
    )
    parser.add_argument(
        "--provider",
        help="Compatibility option: launch the historical provider-specific GUI directly.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable verbose browser logging.",
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


def _first_available_workspace(
    catalog: WorkspaceCatalog,
    registry: ProviderRegistry,
) -> ConversationWorkspace:
    provider_ids = set(registry.provider_ids())
    enabled = tuple(
        item
        for item in catalog.list(enabled_only=True)
        if item.provider_id in provider_ids
    )
    if not enabled:
        raise RuntimeError("No enabled conversation workspace is available.")
    preferred = next((item for item in enabled if item.name == "ChatGPT"), None)
    return preferred or enabled[0]


def _resolve_workspace(
    catalog: WorkspaceCatalog,
    registry: ProviderRegistry,
    requested_name: str | None,
) -> ConversationWorkspace:
    if requested_name:
        workspace = catalog.get(requested_name)
    else:
        workspace = catalog.get_active() or _first_available_workspace(catalog, registry)

    if not workspace.enabled:
        raise ValueError(f"Workspace '{workspace.name}' is disabled")
    if workspace.provider_id not in set(registry.provider_ids()):
        raise ValueError(
            f"Workspace '{workspace.name}' uses unavailable provider: {workspace.provider_id}"
        )
    return workspace


def _launch_shared_shell(
    *,
    catalog: WorkspaceCatalog,
    registry: ProviderRegistry,
    workspace: ConversationWorkspace,
    debug: bool,
) -> int:
    import sqlite3
    import tkinter as tk
    from tkinter import messagebox

    from gpt_exporter.ui.browser import archive_browser as browser
    from gpt_exporter.ui.remote_delete_shell import RemoteDeletionWorkspaceApp

    browser.configure_logging(debug)
    try:
        app = RemoteDeletionWorkspaceApp(
            catalog=catalog,
            registry=registry,
            workspace=workspace,
            action_factory=build_workspace_actions,
            debug=debug,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, str(error), parent=root)
        root.destroy()
        return 1

    catalog.set_active(workspace.name)
    app.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    arguments, provider_arguments = build_parser().parse_known_args(raw_arguments)
    registry = build_provider_registry()
    catalog = build_workspace_catalog(registry, path=arguments.workspace_catalog)

    # Keep the old provider GUIs reachable for scripts/tests during migration.
    # Normal interactive startup no longer opens a provider/workspace chooser.
    if arguments.provider:
        launchers = build_provider_launchers()
        provider_id = arguments.provider
        if provider_id not in launchers:
            raise ValueError(f"Unknown or unavailable provider: {provider_id}")
        workspace = _workspace_for_provider(catalog, provider_id)
        launch_arguments = list(provider_arguments)
        if workspace is not None:
            catalog.set_active(workspace.name)
            launch_arguments = [*workspace_provider_arguments(workspace), *launch_arguments]
        return int(launchers[provider_id](launch_arguments))

    workspace = _resolve_workspace(catalog, registry, arguments.workspace)
    return _launch_shared_shell(
        catalog=catalog,
        registry=registry,
        workspace=workspace,
        debug=arguments.debug,
    )


if __name__ == "__main__":
    raise SystemExit(main())