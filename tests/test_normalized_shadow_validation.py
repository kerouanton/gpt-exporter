import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.index.normalized import index_normalized_file
from gpt_exporter.model import ContentBlock, Conversation, ConversationOrigin, Message
from gpt_exporter.providers import CHATGPT_PROVIDER
from gpt_exporter.providers.base import ExporterProvider
from gpt_exporter.validation import run_normalized_shadow_validation


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "characterization"
    / "conversation_base.json"
)


class NormalizedShadowValidationTests(unittest.TestCase):
    def _provider(self, conversation: Conversation) -> ExporterProvider:
        return ExporterProvider(
            key="chatgpt",
            display_name="Synthetic ChatGPT",
            archive_directory_name="Synthetic Archive",
            website_url="https://example.invalid/",
            source_bundle_name="synthetic.json",
            collector_path=Path(__file__),
            importer=mock.Mock(),
            normalizer=mock.Mock(return_value=conversation),
        )

    def test_shadow_validation_matches_without_mutating_production_database(self) -> None:
        conversation = Conversation(
            provider_key="chatgpt",
            conversation_id="conv-shadow-1",
            title="Shadow validation",
            origins=(
                ConversationOrigin(
                    origin_id="g-p-shadow",
                    origin_type="project",
                    source="message.metadata.gizmo_id",
                ),
            ),
            index_metadata={
                "conversation_template_id": "g-p-shadow",
                "default_model_slug": "gpt-test",
            },
            messages=(
                Message(
                    message_id="m1",
                    author_role="user",
                    text="Hello",
                    content=(ContentBlock(kind="text", text="Hello"),),
                ),
                Message(
                    message_id="m2",
                    author_role="assistant",
                    text="Hi",
                    content=(ContentBlock(kind="text", text="Hi"),),
                ),
            ),
        )
        provider = self._provider(conversation)

        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "archive"
            source = archive / "downloads" / "conv.json.xz"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b"synthetic")
            production_db = archive / "conversations-index.sqlite"

            index_normalized_file(
                provider,
                source,
                archive_root=archive,
                database_path=production_db,
            )
            before = production_db.read_bytes()

            result = run_normalized_shadow_validation(
                provider,
                [source],
                archive_root=archive,
                production_database=production_db,
            )

            after = production_db.read_bytes()
            self.assertEqual(before, after)
            self.assertEqual(result.checked, 1)
            self.assertEqual(result.matched, 1)
            self.assertEqual(result.mismatched, 0)
            self.assertEqual(result.failed, 0)
            self.assertTrue(result.report_path.is_file())
            self.assertTrue(result.shadow_database.is_file())
            self.assertIsNone(result.legacy_oracle_database)
            self.assertTrue(result.conversations[0].provenance_matches)
            self.assertTrue(result.conversations[0].origins_match)
            self.assertIsNone(result.conversations[0].provenance_difference)
            self.assertTrue(
                (archive / "reports" / "provider-validation" / "chatgpt" / "markdown" / "conv-shadow-1.md").is_file()
            )

    def test_real_chatgpt_fixture_matches_legacy_oracle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive = Path(temp_name) / "archive"
            downloads = archive / "downloads"
            downloads.mkdir(parents=True)
            source = downloads / "conversation_base.json"
            source.write_bytes(FIXTURE.read_bytes())
            production_db = archive / "conversations-index.sqlite"

            index_normalized_file(
                CHATGPT_PROVIDER,
                source,
                archive_root=archive,
                database_path=production_db,
            )

            result = run_normalized_shadow_validation(
                CHATGPT_PROVIDER,
                [source],
                archive_root=archive,
                production_database=production_db,
                compare_with_legacy_oracle=True,
            )

            self.assertEqual(result.checked, 1)
            self.assertEqual(result.matched, 1)
            self.assertEqual(result.mismatched, 0)
            self.assertEqual(result.failed, 0)
            self.assertIsNotNone(result.legacy_oracle_database)
            self.assertTrue(result.legacy_oracle_database.is_file())
            conversation = result.conversations[0]
            self.assertTrue(conversation.legacy_matches)
            self.assertEqual(
                conversation.production_message_count,
                conversation.legacy_message_count,
            )
            self.assertIsNone(conversation.legacy_difference)


if __name__ == "__main__":
    unittest.main()
