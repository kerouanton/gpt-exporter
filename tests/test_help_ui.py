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
from gpt_exporter.version import APP_NAME, __version__, display_version, windows_version_tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class HelpUiTests(unittest.TestCase):
    def test_version_metadata_is_consistent(self) -> None:
        metadata = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)
        self.assertEqual(display_version(), "2.9.0")
        self.assertEqual(windows_version_tuple(), (2, 9, 0, 0))

    def test_packaged_help_and_history_are_readable(self) -> None:
        guide = read_user_guide()
        history = read_release_history()

        self.assertIn("# GPT Exporter User Guide", guide)
        self.assertIn("Archive → Archive New Conversations", guide)
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
        rendered = "".join(segment.text for segment in segments)

        self.assertIn("Heading", rendered)
        self.assertIn("• first", rendered)
        self.assertIn("sample", rendered)
        self.assertTrue(any("heading1" in segment.tags for segment in segments if "Heading" in segment.text))
        self.assertTrue(any("strong" in segment.tags for segment in segments if "bold" in segment.text))
        self.assertTrue(any("emphasis" in segment.tags for segment in segments if "emphasis" in segment.text))
        self.assertTrue(any("code" in segment.tags for segment in segments if segment.text == "code"))
        self.assertTrue(any(segment.href == "https://example.com" for segment in segments))
        self.assertTrue(any("code_block" in segment.tags for segment in segments if "sample" in segment.text))

    def test_gui_version_option_uses_central_version_without_import_noise(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "gpt_exporter_gui.py"), "--version"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), f"{APP_NAME} {display_version()}")
        self.assertEqual(completed.stderr, "")

    def test_importing_gui_is_silent(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-c", "import gpt_exporter_gui"],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")

    def test_gui_debug_logging_is_opt_in(self) -> None:
        arguments = gui.build_parser().parse_args([])
        self.assertFalse(arguments.debug)

    def test_windowed_stream_guard_supplies_devnull_streams(self) -> None:
        created_stdout = None
        created_stderr = None
        with patch.object(gui.sys, "stdout", None), patch.object(gui.sys, "stderr", None):
            gui._ensure_standard_streams()
            created_stdout = gui.sys.stdout
            created_stderr = gui.sys.stderr
            self.assertIsNotNone(created_stdout)
            self.assertIsNotNone(created_stderr)
            self.assertFalse(created_stdout.closed)
            self.assertFalse(created_stderr.closed)

        created_stdout.close()
        created_stderr.close()

    def test_help_menu_exposes_guide_history_search_and_about(self) -> None:
        class FakeMenu:
            def __init__(self, master=None, **_kwargs):
                self.master = master
                self.entries = []

            def add_command(self, **kwargs):
                self.entries.append(("command", kwargs))

            def add_separator(self):
                self.entries.append(("separator", {}))

            def add_cascade(self, **kwargs):
                self.entries.append(("cascade", kwargs))

        class FakeApp:
            def __init__(self):
                self.menu = None
                self.current_workspace = gui.BUILTIN_WORKSPACES.get("chatgpt")

            def config(self, **kwargs):
                self.menu = kwargs.get("menu")

            def __getattr__(self, _name):
                return lambda *args, **kwargs: None

        app = FakeApp()
        with patch.object(gui.tk, "Menu", FakeMenu):
            gui.GPTExporterApp._build_menu(app)

        help_entry = next(
            details
            for kind, details in app.menu.entries
            if kind == "cascade" and details.get("label") == "Help"
        )
        help_menu = help_entry["menu"]
        labels = [details.get("label") for kind, details in help_menu.entries if kind == "command"]

        self.assertEqual(
            labels,
            ["User Guide…", "Release History…", "Search Syntax…", "About GPT Exporter…"],
        )


if __name__ == "__main__":
    unittest.main()
