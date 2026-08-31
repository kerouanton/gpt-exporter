import contextlib
import io
import json
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
    def _legacy_render(self, source: Path, assets: Path, markdown: Path) -> str:
        indexed = legacy.discover_local_assets(assets)
        data = legacy.load_json(source)
        active_path = legacy.reconstruct_active_path(data["mapping"], data["current_node"])
        statistics = legacy.ExportStatistics()
        legacy_messages = legacy.extract_visible_messages(
            active_path=active_path,
            statistics=statistics,
            assets=indexed,
            asset_directory=assets,
            markdown_directory=markdown,
        )
        legacy_conversation = legacy.build_conversation(data, legacy_messages)
        return legacy.build_markdown_export(
            legacy_conversation,
            include_timestamps=False,
        )

    def test_chatgpt_core_markdown_matches_legacy_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            assets = root / "assets"
            markdown = root / "markdown"
            assets.mkdir()
            markdown.mkdir()

            expected = self._legacy_render(FIXTURE, assets, markdown)
            normalized = normalize_conversation_file(
                FIXTURE,
                asset_directory=assets,
                markdown_directory=markdown,
            )
            actual = render_conversation_markdown(normalized, include_timestamps=False)

        self.assertEqual(actual, expected)

    def test_chatgpt_core_markdown_matches_legacy_asset_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            assets = root / "assets"
            markdown = root / "markdown"
            image_dir = assets / "image"
            image_dir.mkdir(parents=True)
            markdown.mkdir()
            (image_dir / "file-testimage.png").write_bytes(b"synthetic image bytes")

            source = root / "conversation.json"
            source.write_text(
                json.dumps(
                    {
                        "conversation_id": "conv-asset",
                        "title": "Asset fixture",
                        "current_node": "node-user",
                        "mapping": {
                            "root": {
                                "id": "root",
                                "parent": None,
                                "children": ["node-user"],
                                "message": None,
                            },
                            "node-user": {
                                "id": "node-user",
                                "parent": "root",
                                "children": [],
                                "message": {
                                    "id": "message-user",
                                    "author": {"role": "user"},
                                    "content": {
                                        "content_type": "multimodal_text",
                                        "parts": [
                                            "Here is the image",
                                            {
                                                "content_type": "image_asset_pointer",
                                                "asset_pointer": "sediment://file-testimage",
                                            },
                                        ],
                                    },
                                    "metadata": {},
                                },
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            expected = self._legacy_render(source, assets, markdown)
            normalized = normalize_conversation_file(
                source,
                asset_directory=assets,
                markdown_directory=markdown,
            )
            actual = render_conversation_markdown(normalized, include_timestamps=False)

        self.assertEqual(actual, expected)
        self.assertIn("file-testimage", actual)
        self.assertIn("Archive path:", actual)


if __name__ == "__main__":
    unittest.main()
