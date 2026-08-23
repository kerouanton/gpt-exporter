import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.export.markdown import export_markdown


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class MarkdownLibraryTests(unittest.TestCase):
    def _build_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        downloads = root / "downloads"
        assets = root / "assets"
        markdown = root / "markdown"
        downloads.mkdir(parents=True)
        (assets / "attachment").mkdir(parents=True)
        markdown.mkdir(parents=True)

        attachment = assets / "attachment" / "file_att123__note.txt"
        attachment.write_text("synthetic attachment\n", encoding="utf-8")

        entity_marker = (
            "\ue200entity\ue202"
            "[\"turn0entity0\", \"Visible Entity\"]"
            "\ue201"
        )
        conversation = {
            "title": "Synthetic export",
            "conversation_id": "conv-markdown-001",
            "create_time": 1_700_000_000.0,
            "update_time": 1_700_000_100.0,
            "current_node": "hidden",
            "mapping": {
                "root": {
                    "id": "root",
                    "parent": None,
                    "children": ["user"],
                    "message": None,
                },
                "user": {
                    "id": "user",
                    "parent": "root",
                    "children": ["inactive", "assistant"],
                    "message": {
                        "id": "message-user",
                        "author": {"role": "user"},
                        "create_time": 1_700_000_010.0,
                        "update_time": None,
                        "content": {
                            "content_type": "multimodal_text",
                            "parts": ["Active user question"],
                        },
                        "metadata": {
                            "attachments": [
                                {
                                    "id": "file_att123",
                                    "name": "note.txt",
                                    "mime_type": "text/plain",
                                }
                            ]
                        },
                    },
                },
                "inactive": {
                    "id": "inactive",
                    "parent": "user",
                    "children": [],
                    "message": {
                        "id": "message-inactive",
                        "author": {"role": "assistant"},
                        "create_time": 1_700_000_020.0,
                        "update_time": None,
                        "content": {
                            "content_type": "text",
                            "parts": ["INACTIVE BRANCH MUST NOT APPEAR"],
                        },
                        "metadata": {},
                    },
                },
                "assistant": {
                    "id": "assistant",
                    "parent": "user",
                    "children": ["hidden"],
                    "message": {
                        "id": "message-assistant",
                        "author": {"role": "assistant"},
                        "create_time": 1_700_000_030.0,
                        "update_time": None,
                        "content": {
                            "content_type": "text",
                            "parts": [f"Active answer with {entity_marker}."],
                        },
                        "metadata": {},
                    },
                },
                "hidden": {
                    "id": "hidden",
                    "parent": "assistant",
                    "children": [],
                    "message": {
                        "id": "message-hidden",
                        "author": {"role": "assistant"},
                        "create_time": 1_700_000_040.0,
                        "update_time": None,
                        "content": {
                            "content_type": "text",
                            "parts": ["HIDDEN MESSAGE MUST NOT APPEAR"],
                        },
                        "metadata": {
                            "is_visually_hidden_from_conversation": True
                        },
                    },
                },
            },
        }

        input_path = downloads / "synthetic.json"
        input_path.write_text(
            json.dumps(conversation, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return input_path, assets, markdown

    def test_library_exports_active_branch_assets_and_clean_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            input_path, assets, markdown = self._build_fixture(archive_root)
            output_path = markdown / "synthetic.md"

            result = export_markdown(
                input_path,
                output_path,
                asset_index_path=archive_root / "reports" / "missing-index.json.xz",
                asset_directory=assets,
            )

            text = output_path.read_text(encoding="utf-8")
            self.assertIn("# Synthetic export", text)
            self.assertIn("## Bruno", text)
            self.assertIn("## ChatGPT", text)
            self.assertIn("Active user question", text)
            self.assertIn("Active answer with Visible Entity.", text)
            self.assertIn("Asset ID: `file_att123`", text)
            self.assertIn("../assets/attachment/file_att123__note.txt", text)
            self.assertNotIn("INACTIVE BRANCH MUST NOT APPEAR", text)
            self.assertNotIn("HIDDEN MESSAGE MUST NOT APPEAR", text)
            self.assertNotIn("\ue200", text)

            self.assertEqual(result.output_path, output_path.resolve())
            self.assertEqual(result.conversation_id, "conv-markdown-001")
            self.assertEqual(result.all_nodes, 5)
            self.assertEqual(result.active_nodes, 4)
            self.assertEqual(result.exported_messages, 2)
            self.assertEqual(result.resolved_assets.get("attachment"), 1)
            self.assertEqual(result.cleaned_marker_types.get("entity"), 1)

    def test_library_and_legacy_cli_produce_identical_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            input_path, assets, markdown = self._build_fixture(archive_root)
            library_path = markdown / "library.md"
            cli_path = markdown / "cli.md"
            missing_index = archive_root / "reports" / "missing-index.json.xz"

            export_markdown(
                input_path,
                library_path,
                asset_index_path=missing_index,
                asset_directory=assets,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(REPOSITORY_ROOT / "export_markdown.py"),
                    str(input_path),
                    "--output",
                    str(cli_path),
                    "--asset-index",
                    str(missing_index),
                    "--asset-directory",
                    str(assets),
                    "--quiet",
                ],
                cwd=REPOSITORY_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                library_path.read_bytes(),
                cli_path.read_bytes(),
            )

    def test_library_call_does_not_mutate_sys_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            input_path, assets, markdown = self._build_fixture(archive_root)
            original = sys.argv[:]

            export_markdown(
                input_path,
                markdown / "argv.md",
                asset_index_path=archive_root / "reports" / "missing-index.json.xz",
                asset_directory=assets,
            )

            self.assertEqual(sys.argv, original)

    def test_library_import_has_no_console_or_archive_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = os.environ.copy()
            environment["USERPROFILE"] = temporary

            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import gpt_exporter.export.markdown",
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")
            self.assertFalse(
                (Path(temporary) / "Documents" / "ChatGPT Archive").exists()
            )


if __name__ == "__main__":
    unittest.main()
