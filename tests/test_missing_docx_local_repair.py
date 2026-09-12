from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from gpt_exporter.providers.gpt.export import repair


class MissingDocxLocalRepairTests(unittest.TestCase):
    def _prepare_archive(self, root: Path) -> tuple[Path, Path, Path]:
        downloads = root / "downloads"
        downloads.mkdir(parents=True)

        complete = downloads / "complete.json.xz"
        missing = downloads / "missing.json.xz"
        empty = downloads / "empty.json.xz"
        complete.write_bytes(b"complete-json")
        missing.write_bytes(b"missing-json")
        empty.write_bytes(b"empty-json")

        (root / "complete.docx").write_bytes(b"valid-docx")
        (root / "empty.docx").write_bytes(b"")
        return complete, missing, empty

    def test_find_missing_docx_sources_detects_absent_and_empty_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._prepare_archive(root)

            found = repair.find_missing_docx_sources(root)

            self.assertEqual(
                tuple(path.name for path in found),
                ("empty.json.xz", "missing.json.xz"),
            )

    def test_regenerate_missing_docx_uses_temporary_batch_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            complete, missing, empty = self._prepare_archive(root)
            source_bytes = {
                path: path.read_bytes()
                for path in (complete, missing, empty)
            }
            captured_batch: dict[str, object] = {}

            def fake_export_batch(**kwargs):
                batch_file = Path(kwargs["batch_file"])
                self.assertTrue(batch_file.is_file())
                captured_batch.update(
                    json.loads(batch_file.read_text(encoding="utf-8"))
                )
                self.assertEqual(Path(kwargs["archive_root"]), root.resolve())
                self.assertTrue(kwargs["overwrite_all"])
                return SimpleNamespace(
                    docx_converted=2,
                    success=True,
                )

            with mock.patch.object(repair, "export_batch", side_effect=fake_export_batch) as exporter:
                result = repair.regenerate_missing_docx(root)

            exporter.assert_called_once()
            self.assertEqual(
                captured_batch["conversation_files"],
                ["empty.json.xz", "missing.json.xz"],
            )
            self.assertEqual(
                tuple(path.name for path in result.missing_sources),
                ("empty.json.xz", "missing.json.xz"),
            )
            self.assertEqual(result.repaired_count, 2)
            self.assertTrue(result.success)
            for path, expected in source_bytes.items():
                self.assertEqual(path.read_bytes(), expected)

            self.assertFalse((root / "reports" / "current-batch.json").exists())

    def test_regenerate_missing_docx_is_noop_when_archive_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            downloads.mkdir()
            source = downloads / "complete.json.xz"
            source.write_bytes(b"json")
            (root / "complete.docx").write_bytes(b"docx")

            with mock.patch.object(repair, "export_batch") as exporter:
                result = repair.regenerate_missing_docx(root)

            exporter.assert_not_called()
            self.assertEqual(result.missing_sources, ())
            self.assertEqual(result.repaired_count, 0)
            self.assertTrue(result.success)

    def test_gui_exposes_local_repair_command(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "packages"
            / "export-provider-chatgpt"
            / "src"
            / "export_provider_chatgpt"
            / "ui"
            / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('label="Regenerate Missing DOCX…"', source)
        self.assertIn("command=self.regenerate_missing_docx", source)
        self.assertIn("workflow.MissingDocxRepairDialog", source)


if __name__ == "__main__":
    unittest.main()
