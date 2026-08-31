import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.export.normalized_markdown import render_conversation_markdown
from gpt_exporter.providers.chatgpt_normalizer import normalize_conversation_file

with contextlib.redirect_stdout(io.StringIO()):
    from gpt_exporter.export import _legacy_markdown as legacy


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "characterization"
    / "conversation_base.json"
)


class MarkdownCompatibilityTests(unittest.TestCase):
    def test_chatgpt_core_markdown_matches_legacy_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            assets = root / "assets"
            markdown = root / "markdown"
            assets.mkdir()
            markdown.mkdir()

            data = legacy.load_json(FIXTURE)
            active_path = legacy.reconstruct_active_path(data["mapping"], data["current_node"])
            statistics = legacy.ExportStatistics()
            legacy_messages = legacy.extract_visible_messages(
                active_path=active_path,
                statistics=statistics,
                assets={},
                asset_directory=assets,
                markdown_directory=markdown,
            )
            legacy_conversation = legacy.build_conversation(data, legacy_messages)
            expected = legacy.build_markdown_export(
                legacy_conversation,
                include_timestamps=False,
            )

            normalized = normalize_conversation_file(
                FIXTURE,
                asset_directory=assets,
                markdown_directory=markdown,
            )
            actual = render_conversation_markdown(normalized, include_timestamps=False)

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
