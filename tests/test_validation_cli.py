import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.paths import ArchivePaths
from gpt_exporter.validation_cli import _batch_sources, main


class ValidationCliTests(unittest.TestCase):
    def test_batch_sources_resolve_current_batch_against_archive_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            paths = ArchivePaths.from_root(Path(temp_name) / "archive")
            paths.downloads.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            source = paths.downloads / "conversation.json.xz"
            source.write_bytes(b"compressed-placeholder")
            (paths.reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": [source.name]}),
                encoding="utf-8",
            )

            self.assertEqual(_batch_sources(paths), [source.resolve()])

    def test_main_returns_zero_only_for_complete_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            paths = ArchivePaths.from_root(root)
            paths.downloads.mkdir(parents=True)
            paths.reports.mkdir(parents=True)
            source = paths.downloads / "conversation.json.xz"
            source.write_bytes(b"placeholder")
            (paths.reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": [source.name]}),
                encoding="utf-8",
            )
            result = SimpleNamespace(
                checked=1,
                matched=1,
                mismatched=0,
                failed=0,
                report_path=paths.reports / "provider-validation" / "chatgpt" / "latest.json",
            )

            with mock.patch(
                "gpt_exporter.validation_cli.run_normalized_shadow_validation",
                return_value=result,
            ) as validate:
                return_code = main(["--archive-root", str(root)])

            self.assertEqual(return_code, 0)
            validate.assert_called_once()
            args, kwargs = validate.call_args
            self.assertEqual(args[1], [source.resolve()])
            self.assertTrue(kwargs["compare_with_legacy_oracle"])
            self.assertEqual(kwargs["production_database"], paths.database)


if __name__ == "__main__":
    unittest.main()
