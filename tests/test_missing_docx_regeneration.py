from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.providers.gpt.importer import (
    _augment_current_batch_with_missing_docx,
    _docx_name_for_conversation,
)


class MissingDocxRegenerationTests(unittest.TestCase):
    def test_docx_name_matches_archive_export_name(self) -> None:
        self.assertEqual(
            _docx_name_for_conversation(Path("conversation.json.xz")),
            "conversation.docx",
        )
        self.assertEqual(
            _docx_name_for_conversation(Path("conversation.json")),
            "conversation.docx",
        )

    def test_missing_docx_is_added_to_existing_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            reports = root / "reports"
            downloads.mkdir()
            reports.mkdir()

            existing_json = downloads / "existing.json.xz"
            missing_json = downloads / "missing.json.xz"
            existing_json.write_bytes(b"existing")
            missing_json.write_bytes(b"missing")
            (root / "existing.docx").write_bytes(b"valid docx")
            (reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": []}),
                encoding="utf-8",
            )

            added = _augment_current_batch_with_missing_docx(root)

            self.assertEqual(added, ("missing.json.xz",))
            data = json.loads(
                (reports / "current-batch.json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["conversation_files"], ["missing.json.xz"])

    def test_missing_docx_is_merged_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            reports = root / "reports"
            downloads.mkdir()
            reports.mkdir()

            for name in ("changed.json.xz", "missing.json.xz"):
                (downloads / name).write_bytes(name.encode("ascii"))

            (reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": ["changed.json.xz"]}),
                encoding="utf-8",
            )

            added = _augment_current_batch_with_missing_docx(root)

            self.assertEqual(added, ("missing.json.xz",))
            data = json.loads(
                (reports / "current-batch.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                data["conversation_files"],
                ["changed.json.xz", "missing.json.xz"],
            )

    def test_zero_length_docx_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            reports = root / "reports"
            downloads.mkdir()
            reports.mkdir()

            conversation = downloads / "broken.json.xz"
            conversation.write_bytes(b"json")
            (root / "broken.docx").write_bytes(b"")
            (reports / "current-batch.json").write_text(
                json.dumps({"conversation_files": []}),
                encoding="utf-8",
            )

            added = _augment_current_batch_with_missing_docx(root)
            self.assertEqual(added, ("broken.json.xz",))

    def test_existing_nonempty_docx_does_not_modify_empty_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = root / "downloads"
            reports = root / "reports"
            downloads.mkdir()
            reports.mkdir()

            (downloads / "complete.json.xz").write_bytes(b"json")
            (root / "complete.docx").write_bytes(b"docx")
            batch = reports / "current-batch.json"
            batch.write_text(
                json.dumps({"conversation_files": []}),
                encoding="utf-8",
            )
            before = batch.read_bytes()

            added = _augment_current_batch_with_missing_docx(root)

            self.assertEqual(added, ())
            self.assertEqual(batch.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
