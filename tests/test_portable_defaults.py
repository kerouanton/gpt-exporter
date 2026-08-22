import os
import unittest
from pathlib import Path

import archive_browser
import index_chatgpt_archive as indexer


class PortableDefaultPathTests(unittest.TestCase):
    def test_indexer_default_archive_root_uses_user_profile(self) -> None:
        expected_root = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents" / "ChatGPT Archive"
        self.assertEqual(indexer.DEFAULT_ARCHIVE_ROOT, expected_root)
        self.assertEqual(indexer.DEFAULT_DATABASE_PATH, expected_root / "conversations-index.sqlite")

    def test_browser_default_database_path_uses_user_profile(self) -> None:
        expected_root = Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents" / "ChatGPT Archive"
        self.assertEqual(archive_browser.DEFAULT_DATABASE_PATH, expected_root / "conversations-index.sqlite")


if __name__ == "__main__":
    unittest.main()
