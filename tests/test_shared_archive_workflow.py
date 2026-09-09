import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.providers.discord.collector import EXPORTER_NAME, SCHEMA_VERSION
from gpt_exporter.providers.discord.ui.workspace_actions import DiscordWorkspaceActions
from gpt_exporter.providers.gpt.ui.workspace_actions import GPTWorkspaceActions
from gpt_exporter.ui.archive_workflow import ArchiveWorkflowSpec


class SharedArchiveWorkflowTests(unittest.TestCase):
    def test_both_providers_expose_shared_workflow_specs(self) -> None:
        self.assertIsInstance(GPTWorkspaceActions.archive_workflow_spec, ArchiveWorkflowSpec)
        self.assertIsInstance(DiscordWorkspaceActions.archive_workflow_spec, ArchiveWorkflowSpec)
        self.assertEqual(GPTWorkspaceActions.archive_workflow_spec.service_label, "ChatGPT")
        self.assertEqual(DiscordWorkspaceActions.archive_workflow_spec.service_label, "Discord")

    def test_chatgpt_archive_new_uses_shared_dialog(self) -> None:
        app = object()
        actions = GPTWorkspaceActions(app, SimpleNamespace(root_path=Path("C:/archive")))

        with mock.patch(
            "gpt_exporter.providers.gpt.ui.workspace_actions.ArchiveWorkflowDialog"
        ) as dialog:
            actions.archive_new()

        dialog.assert_called_once_with(app, actions=actions)

    def test_discord_archive_new_uses_shared_dialog(self) -> None:
        app = object()
        actions = DiscordWorkspaceActions(app, SimpleNamespace(root_path=Path("C:/archive")))

        with mock.patch(
            "gpt_exporter.providers.discord.ui.workspace_actions.ArchiveWorkflowDialog"
        ) as dialog:
            actions.archive_new()

        dialog.assert_called_once_with(app, actions=actions)

    def test_chatgpt_process_export_uses_shared_processing_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            bundle = Path(temp_name) / "chatgpt-archive-source.json"
            bundle.write_text("{}", encoding="utf-8")
            app = SimpleNamespace(status_var=mock.Mock())
            actions = GPTWorkspaceActions(app, SimpleNamespace(root_path=Path(temp_name) / "archive"))

            with mock.patch(
                "gpt_exporter.providers.gpt.ui.workspace_actions.ArchiveProcessingDialog"
            ) as dialog:
                self.assertTrue(actions.process_export(bundle))

            dialog.assert_called_once_with(app, actions=actions, export_path=bundle)

    def test_discord_process_export_uses_shared_processing_backlog(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            downloads = Path(temp_name)
            export_path = downloads / "discord-dm-export-v15_shared-test.json"
            export_path.write_text(
                json.dumps(
                    {
                        "exporter": EXPORTER_NAME,
                        "schema_version": SCHEMA_VERSION,
                        "exported_at": "2026-09-09T12:00:00Z",
                        "message_count": 1,
                        "conversation": {
                            "channel_id": "1093985962649976892",
                            "title": "Shared workflow test",
                        },
                        "messages": [{"id": "1093985962649976893"}],
                    }
                ),
                encoding="utf-8",
            )
            app = SimpleNamespace(status_var=mock.Mock())
            actions = DiscordWorkspaceActions(app, SimpleNamespace(root_path=downloads / "archive"))

            with mock.patch(
                "gpt_exporter.providers.discord.ui.workspace_actions.ArchiveProcessingDialog"
            ) as dialog:
                self.assertTrue(actions.process_export(export_path))

            dialog.assert_called_once_with(app, actions=actions, export_path=export_path)

    def test_discord_run_export_reports_backlog_lines(self) -> None:
        app = object()
        actions = DiscordWorkspaceActions(app, SimpleNamespace(root_path=Path("C:/archive")))
        result = SimpleNamespace(
            message_count=12,
            available_assets=4,
            downloaded_assets=2,
            reused_assets=2,
            failed_assets=(),
            raw_path=Path("C:/archive/raw/test.json.xz"),
            canonical_path=Path("C:/archive/downloads/test.json.xz"),
            docx_path=Path("C:/archive/test.docx"),
            database_path=Path("C:/archive/conversations-index.sqlite"),
        )
        lines: list[str] = []

        with mock.patch(
            "gpt_exporter.providers.discord.ui.workspace_actions.archive_collector_export",
            return_value=result,
        ) as archive:
            self.assertIs(actions.run_export(Path("C:/Downloads/export.json"), lines.append), result)

        archive.assert_called_once_with(
            Path("C:/Downloads/export.json"), archive_root=Path("C:/archive")
        )
        self.assertTrue(any("12 message" in line for line in lines))
        self.assertTrue(any("Assets:" in line for line in lines))
        self.assertTrue(any("DOCX:" in line for line in lines))

    def test_chatgpt_new_export_detection_ignores_initial_bundle(self) -> None:
        actions = GPTWorkspaceActions(object(), SimpleNamespace(root_path=Path("C:/archive")))
        bundle = Path("C:/Downloads/chatgpt-archive-source.json")

        with mock.patch(
            "gpt_exporter.providers.gpt.ui.workspace_actions.workflow.find_latest_source_bundle",
            return_value=bundle,
        ), mock.patch(
            "gpt_exporter.providers.gpt.ui.workspace_actions.workflow.source_bundle_signature",
            return_value=("bundle", 1, 10),
        ):
            self.assertIsNone(actions.find_new_export(("bundle", 1, 10)))
            self.assertEqual(actions.find_new_export(("bundle", 0, 5)), bundle)

    def test_discord_new_export_detection_uses_snapshot_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            downloads = Path(temp_name)
            actions = DiscordWorkspaceActions(
                object(),
                SimpleNamespace(root_path=downloads / "archive"),
            )
            actions.download_directory = downloads
            snapshot = actions.snapshot_exports()

            export_path = downloads / "discord-dm-export-v15_shared-test.json"
            export_path.write_text(
                json.dumps(
                    {
                        "exporter": EXPORTER_NAME,
                        "schema_version": SCHEMA_VERSION,
                        "exported_at": "2026-09-09T12:00:00Z",
                        "message_count": 1,
                        "conversation": {
                            "channel_id": "1093985962649976892",
                            "title": "Shared workflow test",
                        },
                        "messages": [{"id": "1093985962649976893"}],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(actions.find_new_export(snapshot), export_path.resolve())


if __name__ == "__main__":
    unittest.main()
