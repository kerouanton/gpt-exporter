import shutil
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.export.batch import export_batch
from gpt_exporter.export.normalized_batch import export_normalized_batch
from gpt_exporter.providers import CHATGPT_PROVIDER


FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "characterization"
    / "conversation_base.json"
)


class NormalizedBatchExportTests(unittest.TestCase):
    def _archive(self, parent: Path, name: str) -> Path:
        root = parent / name
        for directory in (root / "downloads", root / "assets", root / "reports"):
            directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FIXTURE, root / "downloads" / "conversation_base.json")
        return root

    def test_markdown_only_batch_matches_historical_export_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            parent = Path(temp_name)
            legacy_root = self._archive(parent, "legacy")
            core_root = self._archive(parent, "core")

            legacy_result = export_batch(
                archive_root=legacy_root,
                markdown_only=True,
                overwrite_all=True,
            )
            core_result = export_normalized_batch(
                CHATGPT_PROVIDER,
                archive_root=core_root,
                markdown_only=True,
                overwrite_all=True,
            )

            legacy_files = sorted((legacy_root / "markdown").glob("*.md"))
            core_files = sorted((core_root / "markdown").glob("*.md"))
            self.assertTrue(legacy_result.success)
            self.assertTrue(core_result.success)
            self.assertEqual([path.name for path in core_files], [path.name for path in legacy_files])
            self.assertEqual(len(core_files), 1)
            self.assertEqual(
                core_files[0].read_text(encoding="utf-8"),
                legacy_files[0].read_text(encoding="utf-8"),
            )
            self.assertEqual(core_result.requested, legacy_result.requested)
            self.assertEqual(core_result.markdown_converted, legacy_result.markdown_converted)
            self.assertEqual(core_result.markdown_skipped, legacy_result.markdown_skipped)


if __name__ == "__main__":
    unittest.main()
