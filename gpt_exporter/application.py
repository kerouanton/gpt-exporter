"""Top-level application composition for named conversation workspaces."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from gpt_exporter.core import ProviderRegistry
from gpt_exporter.provider_manager import ProviderManager
from gpt_exporter.version import APP_NAME, display_version
from gpt_exporter.workspaces import ConversationWorkspace, WorkspaceCatalog

ProviderLauncher = Callable[[list[str]], int]


def build_provider_registry() -> ProviderRegistry:
    """Discover installed/in-tree providers and honor durable enable/disable state."""

    return ProviderManager.discover().registry


def build_default_workspaces(registry: ProviderRegistry) -> tuple[ConversationWorkspace, ...]:
    """Compose provider-owned defaults into provider-neutral named workspaces."""

    workspaces: list[ConversationWorkspace] = []
    for provider in registry.providers():
        factory = getattr(provider, "default_workspaces", None)
        if not callable(factory):
            continue
        for workspace in factory():
            if workspace.provider_id != provider.descriptor.provider_id:
                raise ValueError(
                    f"Provider {provider.descriptor.provider_id} returned a workspace for {workspace.provider_id}"
                )
            workspaces.append(workspace)
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


def build_provider_launchers(
    registry: ProviderRegistry | None = None,
) -> dict[str, ProviderLauncher]:
    """Build compatibility launchers from optional provider capabilities."""

    registry = registry or build_provider_registry()
    launchers: dict[str, ProviderLauncher] = {}
    for provider in registry.providers():
        legacy_main = getattr(provider, "legacy_main", None)
        if not callable(legacy_main):
            continue

        def launch(arguments: list[str], *, _provider=provider) -> int:
            provider_main = _provider.legacy_main()
            return _run_provider_main(provider_main, arguments)

        launchers[provider.descriptor.provider_id] = launch
    return launchers


def workspace_provider_arguments(
    workspace: ConversationWorkspace,
    registry: ProviderRegistry | None = None,
) -> list[str]:
    """Ask the owning provider to translate a workspace into legacy CLI inputs."""

    registry = registry or build_provider_registry()
    provider = registry.get(workspace.provider_id)
    factory = getattr(provider, "workspace_arguments", None)
    if not callable(factory):
        return []
    return list(factory(workspace))


def build_workspace_actions(
    app,
    workspace: ConversationWorkspace,
    registry: ProviderRegistry | None = None,
):
    """Build provider commands for the common workspace shell through provider hooks."""

    registry = registry or build_provider_registry()
    provider = registry.get(workspace.provider_id)
    factory = getattr(provider, "build_workspace_actions", None)
    if not callable(factory):
        raise ValueError(
            f"No shared-shell actions are registered for provider: {workspace.provider_id}"
        )
    return factory(app, workspace)


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
        help="Compatibility option: launch a provider-specific GUI directly when available.",
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
    return enabled[0]


def _resolve_workspace(
    catalog: WorkspaceCatalog,
    registry: ProviderRegistry,
    requested_name: str | None,
) -> ConversationWorkspace:
    if requested_name:
        workspace = catalog.get(requested_name)
    else:
        active = catalog.get_active()
        available_ids = set(registry.provider_ids())
        workspace = (
            active
            if active is not None and active.provider_id in available_ids and active.enabled
            else _first_available_workspace(catalog, registry)
        )

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
            action_factory=lambda owner, selected: build_workspace_actions(
                owner,
                selected,
                registry=registry,
            ),
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

    # Keep provider-owned compatibility GUIs reachable during migration.
    if arguments.provider:
        launchers = build_provider_launchers(registry)
        provider_id = arguments.provider
        if provider_id not in launchers:
            raise ValueError(f"Unknown, disabled or unavailable provider: {provider_id}")
        workspace = _workspace_for_provider(catalog, provider_id)
        launch_arguments = list(provider_arguments)
        if workspace is not None:
            catalog.set_active(workspace.name)
            launch_arguments = [
                *workspace_provider_arguments(workspace, registry=registry),
                *launch_arguments,
            ]
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
