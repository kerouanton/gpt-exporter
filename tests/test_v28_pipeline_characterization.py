import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import archive_chats


class V28PipelineCharacterizationTests(unittest.TestCase):
    def test_cli_delegates_default_v28_options_to_library_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            with (
                mock.patch.object(
                    archive_chats,
                    "default_archive_paths",
                    return_value=SimpleNamespace(root=archive_root),
                ),
                mock.patch.object(archive_chats, "archive_bundle") as archive_bundle,
                mock.patch.object(sys, "argv", ["archive_chats.py"]),
            ):
                result = archive_chats.main()

        self.assertEqual(result, 0)
        archive_bundle.assert_called_once_with(
            archive_root=archive_root,
            convert_only=False,
            fresh=False,
            skip_assets=False,
            legacy_root=archive_chats.ROOT,
            progress=print,
        )

    def test_cli_preserves_convert_fresh_and_skip_assets_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive_root = Path(temporary) / "archive"
            with (
                mock.patch.object(
                    archive_chats,
                    "default_archive_paths",
                    return_value=SimpleNamespace(root=archive_root),
                ),
                mock.patch.object(archive_chats, "archive_bundle") as archive_bundle,
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "archive_chats.py",
                        "--convert-only",
                        "--fresh",
                        "--skip-assets",
                    ],
                ),
            ):
                result = archive_chats.main()

        self.assertEqual(result, 0)
        archive_bundle.assert_called_once_with(
            archive_root=archive_root,
            convert_only=True,
            fresh=True,
            skip_assets=True,
            legacy_root=archive_chats.ROOT,
            progress=print,
        )

    def test_cli_returns_one_when_pipeline_reports_runtime_failure(self) -> None:
        captured = io.StringIO()
        with (
            mock.patch.object(
                archive_chats,
                "archive_bundle",
                side_effect=RuntimeError("synthetic pipeline failure"),
            ),
            mock.patch.object(sys, "argv", ["archive_chats.py"]),
            contextlib.redirect_stderr(captured),
        ):
            result = archive_chats.main()

        self.assertEqual(result, 1)
        self.assertIn("ERROR: synthetic pipeline failure", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
