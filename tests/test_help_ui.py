import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import gpt_exporter_gui as gui
from gpt_exporter.resources import read_release_history, read_user_guide
from gpt_exporter.ui.markdown_viewer import markdown_segments
from gpt_exporter.version import APP_NAME, APP_SHORT_NAME, __version__, display_version, windows_version_tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class HelpUiTests(unittest.TestCase):
    def test_version_metadata_is_consistent(self) -> None:
        metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)
        self.assertEqual(display_version(), "2.10.0")
        self.assertEqual(windows_version_tuple(), (2, 10, 0, 0))

    def test_packaged_help_and_history_are_readable(self) -> None:
        guide = read_user_guide()
        history = read_release_history()

        self.assertIn(APP_NAME, guide)
        self.assertIn(APP_SHORT_NAME, guide)
        self.assertIn("## Archiving new or updated conversations", guide)
        self.assertIn("# GPT Exporter Release History", history)
        self.assertIn("v2.9", history)
        self.assertIn("v2.8", history)

    def test_markdown_render_model_preserves_common_document_semantics(self) -> None:
        source = """# Heading

Paragraph with **bold**, *emphasis*, `code`, and a [link](https://example.com).

- first
- second

```text
sample
```
"""
        segments = markdown_segments(source)
        kinds = [segment.kind for segment in segments]
        self.assertIn("heading", kinds)
        self.assertIn("paragraph", kinds)
        self.assertIn("bullet", kinds)
        self.assertIn("code", kinds)

        paragraph = next(segment for segment in segments if segment.kind == "paragraph")
        self.assertTrue(any(run.bold for run in paragraph.runs))
        self.assertTrue(any(run.italic for run in paragraph.runs))
        self.assertTrue(any(run.code for run in paragraph.runs))
        self.assertTrue(any(run.url == "https://example.com" for run in paragraph.runs))

    def test_gui_version_option_uses_central_version_without_import_noise(self) -> None:
        result = subprocess.run(
            [sys.executable, "gpt_exporter_gui.py", "--version"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"{APP_NAME} {display_version()}")
        self.assertEqual(result.stderr, "")

    def test_importing_gui_is_silent(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", "import gpt_exporter_gui"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_packaged_help_and_history_are_readable(self) -> None:
        guide = read_user_guide()
        history = read_release_history()

        self.assertIn(APP_NAME, guide)
        self.assertIn(APP_SHORT_NAME, guide)
        self.assertIn("## Archiving new or updated conversations", guide)
        self.assertIn("# GPT Exporter Release History", history)
        self.assertIn("v2.9", history)
        self.assertIn("v2.8", history)

    def test_help_menu_exposes_guide_history_search_and_about(self) -> None:
        self.assertIn("User Guide", gui.HELP_MENU_LABELS)
        self.assertIn("Release History", gui.HELP_MENU_LABELS)
        self.assertIn("Search Help", gui.HELP_MENU_LABELS)
        self.assertIn("About", gui.HELP_MENU_LABELS)

    def test_gui_debug_logging_is_opt_in(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(gui.debug_logging_enabled())
        with patch.dict(os.environ, {"GPT_EXPORTER_DEBUG": "1"}, clear=True):
            self.assertTrue(gui.debug_logging_enabled())

    def test_windowed_stream_guard_supplies_devnull_streams(self) -> None:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        try:
            sys.stdout = None
            sys.stderr = None
            gui.ensure_windowed_streams()
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
            self.assertTrue(hasattr(sys.stdout, "write"))
            self.assertTrue(hasattr(sys.stderr, "write"))
            sys.stdout.close()
            sys.stderr.close()
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    unittest.main()
