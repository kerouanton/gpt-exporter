import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import tempfile
import time
import unittest
from pathlib import Path

from gpt_exporter import acquisition
from gpt_exporter.providers import CHATGPT_PROVIDER


class AcquisitionCoreTests(unittest.TestCase):
    def test_windows_download_directories_are_unique(self) -> None:
        directories = acquisition.windows_download_directories(
            {
                "USERPROFILE": r"C:\Users\Example",
                "HOMEDRIVE": "C:",
                "HOMEPATH": r"\Users\Example",
            },
            home=Path(r"C:\Users\Example"),
        )

        normalized = [os.path.normcase(os.path.abspath(str(path))) for path in directories]
        self.assertEqual(len(normalized), len(set(normalized)))

    def test_find_source_bundle_uses_provider_bundle_name(self) -> None:
        with tempfile.TemporaryDirectory() as first_name, tempfile.TemporaryDirectory() as second_name:
            first = Path(first_name)
            second = Path(second_name)
            older = first / CHATGPT_PROVIDER.source_bundle_name
            newer = second / CHATGPT_PROVIDER.source_bundle_name
            older.write_text("older", encoding="utf-8")
            time.sleep(0.01)
            newer.write_text("newer", encoding="utf-8")

            found = acquisition.find_source_bundle(
                CHATGPT_PROVIDER,
                download_directories=[first, second],
            )

            self.assertEqual(found, newer)

    def test_find_source_bundle_ignores_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name)
            (directory / CHATGPT_PROVIDER.source_bundle_name).write_bytes(b"")

            self.assertIsNone(
                acquisition.find_source_bundle(
                    CHATGPT_PROVIDER,
                    download_directories=[directory],
                )
            )

    def test_collection_instructions_are_provider_driven(self) -> None:
        instructions = "\n".join(
            acquisition.bundle_creation_instructions(CHATGPT_PROVIDER)
        )

        self.assertIn(CHATGPT_PROVIDER.website_url, instructions)
        self.assertIn(CHATGPT_PROVIDER.source_bundle_name, instructions)
        self.assertIn(CHATGPT_PROVIDER.collector_name, instructions)

    def test_require_source_bundle_reports_provider_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            lines: list[str] = []
            with self.assertRaises(FileNotFoundError) as caught:
                acquisition.require_source_bundle(
                    CHATGPT_PROVIDER,
                    download_directories=[Path(temp_name)],
                    progress=lines.append,
                )

        self.assertIn(CHATGPT_PROVIDER.source_bundle_name, str(caught.exception))
        self.assertTrue(any(CHATGPT_PROVIDER.website_url in line for line in lines))

    def test_delete_consumed_source_bundle_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "source.json"
            path.write_text("source", encoding="utf-8")

            deleted = acquisition.delete_consumed_source_bundle(path)

            self.assertTrue(deleted)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
