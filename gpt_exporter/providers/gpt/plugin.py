"""Application-composition hooks for the in-tree ChatGPT provider package."""

from __future__ import annotations

from gpt_exporter.core import ProviderDescriptor
from gpt_exporter.workspaces import ConversationWorkspace

from .provider import ChatGPTProvider


class ChatGPTPlugin(ChatGPTProvider):
    """ChatGPT ingestion plus optional application/workspace capabilities."""

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id="gpt",
            display_name="ChatGPT",
            version="1",
            capabilities=(
                "default-workspace",
                "legacy-ui",
                "workspace-actions",
                "workspace-arguments",
            ),
        )

    def default_workspaces(self) -> tuple[ConversationWorkspace, ...]:
        from .paths import default_archive_paths

        return (
            ConversationWorkspace(
                name="ChatGPT",
                provider_id=self.descriptor.provider_id,
                root_path=default_archive_paths().root,
                description="Default ChatGPT conversation archive.",
            ),
        )

    def legacy_main(self):
        from .ui import app as provider_app

        return provider_app.main

    def workspace_arguments(self, workspace: ConversationWorkspace) -> list[str]:
        return ["--database", str(workspace.database_path)]

    def build_workspace_actions(self, app, workspace: ConversationWorkspace):
        from .ui.workspace_actions import GPTWorkspaceActions

        return GPTWorkspaceActions(app, workspace)


def create_provider() -> ChatGPTPlugin:
    """Entry-point compatible provider factory."""

    return ChatGPTPlugin()


__all__ = ["ChatGPTPlugin", "create_provider"]
