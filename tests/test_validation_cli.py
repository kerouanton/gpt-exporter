import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.paths import ArchivePaths
from gpt_exporter.validation_cli import (
    _augment_report_with_markdown_excerpts,
    _batch_sources,
    _mismatched_sources,
    main,
)


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

    def test_mismatched_sources_reads_previous_report_before_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            paths = ArchivePaths.from_root(Path(temp_name) / "archive")
            paths.downloads.mkdir(parents=True)
            report = paths.reports / "provider-validation" / "chatgpt" / "latest.json"
            report.parent.mkdir(parents=True)
            matched = paths.downloads / "matched.json.xz"
            mismatched = paths.downloads / "mismatched.json.xz"
            matched.write_bytes(b"matched")
            mismatched.write_bytes(b"mismatched")
            report.write_text(
                json.dumps(
                    {
                        "conversations": [
                            {
                                "source": str(matched),
                                "title_matches": True,
                                "message_count_matches": True,
                                "message_content_matches": True,
                                "provenance_matches": True,
                                "origins_match": True,
                                "legacy_matches": True,
                                "markdown_legacy_matches": True,
                                "docx_legacy_matches": True,
                            },
                            {
                                "source": str(mismatched),
                                "title_matches": True,
                                "message_count_matches": True,
                                "message_content_matches": True,
                                "provenance_matches": True,
                                "origins_match": True,
                                "legacy_matches": True,
                                "markdown_legacy_matches": False,
                                "docx_legacy_matches": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(_mismatched_sources(paths, "chatgpt"), [mismatched.resolve()])

    def test_report_is_augmented_with_first_markdown_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            validation_root = Path(temp_name) / "reports" / "provider-validation" / "chatgpt"
            oracle = validation_root / "export-oracle"
            oracle.mkdir(parents=True)
            report = validation_root / "latest.json"
            report.write_text(
                json.dumps(
                    {
                        "conversations": [
                            {
                                "conversation_id": "conv-1",
                                "markdown_legacy_matches": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (oracle / "conv-1-legacy.md").write_text("same\nlegacy line\nafter\n", encoding="utf-8")
            (oracle / "conv-1-core.md").write_text("same\ncore line\nafter\n", encoding="utf-8")

            _augment_report_with_markdown_excerpts(report)

            payload = json.loads(report.read_text(encoding="utf-8"))
            excerpt = payload["conversations"][0]["markdown_excerpt"]
            self.assertEqual(excerpt["line"], 2)
            self.assertEqual(excerpt["legacy"], "legacy line")
            self.assertEqual(excerpt["core"], "core line")
            self.assertEqual(excerpt["legacy_context"], ["same", "legacy line", "after"])
            self.assertEqual(excerpt["core_context"], ["same", "core line", "after"])

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
            self.assertEqual(Path(kwargs["production_database"]).name, "conversations-index.sqlite")
            self.assertEqual(Path(kwargs["production_database"]).parent.name, "archive")

    def test_main_mismatched_mode_uses_previous_report_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name) / "archive"
            paths = ArchivePaths.from_root(root)
            paths.downloads.mkdir(parents=True)
            source = paths.downloads / "bad.json.xz"
            source.write_bytes(b"placeholder")
            report = paths.reports / "provider-validation" / "chatgpt" / "latest.json"
            report.parent.mkdir(parents=True)
            report.write_text(
                json.dumps(
                    {
                        "conversations": [
                            {
                                "source": str(source),
                                "markdown_legacy_matches": False,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = SimpleNamespace(
                checked=1,
                matched=0,
                mismatched=1,
                failed=0,
                report_path=report,
            )

            with (
                mock.patch(
                    "gpt_exporter.validation_cli.run_normalized_shadow_validation",
                    return_value=result,
                ) as validate,
                mock.patch("gpt_exporter.validation_cli._augment_report_with_markdown_excerpts"),
            ):
                return_code = main(["--archive-root", str(root), "--mismatched"])

            self.assertEqual(return_code, 1)
            self.assertEqual(validate.call_args.args[1], [source.resolve()])


if __name__ == "__main__":
    unittest.main()
