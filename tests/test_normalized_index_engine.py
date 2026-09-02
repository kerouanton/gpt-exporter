import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gpt_exporter.index.normalized_engine import update_normalized_index
from gpt_exporter.model import Conversation, Message
from gpt_exporter.providers.base import ExporterProvider


class NormalizedIndexEngineTests(unittest.TestCase):
    def test_incremental_update_matches_historical_mtime_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            downloads = root / "downloads"
            downloads.mkdir(parents=True)
            source = downloads / "conversation.json.xz"
            source.write_bytes(b"first")

            conversation = Conversation(
                provider_key="chatgpt",
                conversation_id="conv-1",
                title="Conversation",
                messages=(
                    Message(
                        message_id="m1",
                        author_role="user",
                        text="Hello",
                        search_text="Hello",
                        is_visible=True,
                        is_indexable=True,
                        display_order=1,
                        search_order=1,
                    ),
                ),
            )
            normalizer = mock.Mock(return_value=conversation)
            provider = ExporterProvider(
                key="chatgpt",
                display_name="ChatGPT",
                archive_directory_name="ChatGPT Archive",
                website_url="https://example.invalid/",
                source_bundle_name="source.json",
                collector_path=Path(__file__),
                importer=mock.Mock(),
                normalizer=normalizer,
            )

            first = update_normalized_index(provider, root)
            self.assertEqual(normalizer.call_count, 1)

            second = update_normalized_index(provider, root)

            self.assertEqual(first.total_files, 1)
            self.assertEqual(first.updated, 1)
            self.assertEqual(first.unchanged_or_skipped, 0)
            self.assertEqual(first.failed, 0)
            self.assertEqual(second.updated, 0)
            self.assertEqual(second.unchanged_or_skipped, 1)
            self.assertEqual(second.failed, 0)
            # Exact same archived path + mtime is skipped before the potentially
            # expensive provider normalizer runs.
            self.assertEqual(normalizer.call_count, 1)

            previous_mtime = source.stat().st_mtime_ns
            source.write_bytes(b"second")
            os.utime(source, ns=(previous_mtime + 1_000_000, previous_mtime + 1_000_000))
            third = update_normalized_index(provider, root)

            self.assertEqual(third.updated, 1)
            self.assertEqual(third.unchanged_or_skipped, 0)
            self.assertEqual(third.failed, 0)
            self.assertEqual(normalizer.call_count, 2)

    def test_renamed_source_is_normalized_even_when_mtime_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            downloads = root / "downloads"
            downloads.mkdir(parents=True)
            source = downloads / "conversation.json.xz"
            source.write_bytes(b"first")

            conversation = Conversation(
                provider_key="chatgpt",
                conversation_id="conv-1",
                title="Conversation",
                messages=(
                    Message(
                        message_id="m1",
                        author_role="user",
                        text="Hello",
                        search_text="Hello",
                        is_visible=True,
                        is_indexable=True,
                        display_order=1,
                        search_order=1,
                    ),
                ),
            )
            normalizer = mock.Mock(return_value=conversation)
            provider = ExporterProvider(
                key="chatgpt",
                display_name="ChatGPT",
                archive_directory_name="ChatGPT Archive",
                website_url="https://example.invalid/",
                source_bundle_name="source.json",
                collector_path=Path(__file__),
                importer=mock.Mock(),
                normalizer=normalizer,
            )

            first = update_normalized_index(provider, root)
            self.assertEqual(first.updated, 1)

            renamed = downloads / "renamed.json.xz"
            source.rename(renamed)
            second = update_normalized_index(provider, root)

            self.assertEqual(second.updated, 0)
            self.assertEqual(second.unchanged_or_skipped, 1)
            # The path changed, so the engine cannot use the source-path fast
            # path and must normalize to recover the native conversation id.
            self.assertEqual(normalizer.call_count, 2)


if __name__ == "__main__":
    unittest.main()
