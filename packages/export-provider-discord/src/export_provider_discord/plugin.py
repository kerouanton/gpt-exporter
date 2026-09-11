"""Application-composition hooks for the in-tree Discord provider package."""

from __future__ import annotations

from gpt_exporter.core import ProviderDescriptor
from gpt_exporter.workspaces import ConversationWorkspace

from .provider import DiscordProvider


class DiscordPlugin(DiscordProvider):
    """Discord ingestion plus optional application/workspace capabilities."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="discord",
            display_name="Discord",
            version="2",
            capabilities=(
                "default-workspace",
                "legacy-ui",
                "workspace-actions",
                "workspace-arguments",
            ),
        )

    def default_workspaces(self) -> tuple[ConversationWorkspace, ...]:
        from .archive import default_archive_root

        return (
            ConversationWorkspace(
                name="Discord",
                provider_id=self.descriptor.provider_id,
                root_path=default_archive_root(),
                description="Default Discord conversation archive.",
            ),
        )

    def legacy_main(self):
        from .ui import app as provider_app

        return provider_app.main

    def workspace_arguments(self, workspace: ConversationWorkspace) -> list[str]:
        return ["--archive-root", str(workspace.root_path)]

    def build_workspace_actions(self, app, workspace: ConversationWorkspace):
        from .ui.remote_delete_actions import DiscordRemoteDeleteActions

        return DiscordRemoteDeleteActions(app, workspace)


def create_provider() -> DiscordPlugin:
    """Entry-point compatible provider factory."""

    return DiscordPlugin()


__all__ = ["DiscordPlugin", "create_provider"]
