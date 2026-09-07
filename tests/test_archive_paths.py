import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

import archive_chats
import index_chatgpt_archive as indexer
from gpt_exporter.paths import ArchivePaths, default_archive_paths, default_legacy_paths, default_user_profile


class ArchivePathsTests(unittest.TestCase):
    def test_from_root_derives_all_canonical_paths(self) -> None:
        root = Path("C:/synthetic/archive")
        paths = ArchivePaths.from_root(root)

        self.assertEqual(paths.root, root)
        self.assertEqual(paths.downloads, root / "downloads")
        self.assertEqual(paths.assets, root / "assets")
        self.assertEqual(paths.reports, root / "reports")
        self.assertEqual(paths.markdown, root / "markdown")
        self.assertEqual(paths.database, root / "conversations-index.sqlite")

    def test_from_root_derives_canonical_legacy_paths(self) -> None:
        root = Path("C:/synthetic/archive")
        legacy = ArchivePaths.from_root(root).legacy

        self.assertEqual(legacy.root, root / "legacy")
        self.assertEqual(legacy.sources, root / "legacy" / "sources")
        self.assertEqual(legacy.normalized_docx, root / "legacy" / "normalized-docx")
        self.assertEqual(legacy.reconstruction, root / "legacy" / "reconstruction")
        self.assertEqual(legacy.turns, root / "legacy" / "reconstruction" / "legacy-docx-turns.json")
        self.assertEqual(
            legacy.semantic_audit_json,
            root / "legacy" / "reconstruction" / "legacy-semantic-audit.json",
        )
        self.assertEqual(
            legacy.semantic_audit_csv,
            root / "legacy" / "reconstruction" / "legacy-semantic-audit.csv",
        )

    def test_default_legacy_paths_follow_user_profile(self) -> None:
        legacy = default_legacy_paths({"USERPROFILE": "C:/Users/Synthetic"})
        expected = Path("C:/Users/Synthetic/Documents/ChatGPT Archive/legacy")

        self.assertEqual(legacy.root, expected)
        self.assertEqual(legacy.sources, expected / "sources")
        self.assertEqual(legacy.normalized_docx, expected / "normalized-docx")
        self.assertEqual(legacy.turns, expected / "reconstruction" / "legacy-docx-turns.json")

    def test_default_user_profile_prefers_userprofile(self) -> None:
        environment = {"USERPROFILE": "C:/Users/Synthetic"}

        profile = default_user_profile(environment, home=Path("C:/Fallback"))

        self.assertEqual(profile, Path("C:/Users/Synthetic"))

    def test_default_user_profile_falls_back_to_home(self) -> None:
        profile = default_user_profile({}, home=Path("C:/Fallback"))

        self.assertEqual(profile, Path("C:/Fallback"))

    def test_default_archive_paths_preserve_v28_constants(self) -> None:
        paths = default_archive_paths()

        self.assertEqual(paths.root, archive_chats.ARCHIVE_ROOT)
        self.assertEqual(paths.downloads, archive_chats.DOWNLOADS_DIR)
        self.assertEqual(paths.assets, archive_chats.ASSETS_DIR)
        self.assertEqual(paths.reports, archive_chats.REPORTS_DIR)
        self.assertEqual(paths.markdown, archive_chats.MARKDOWN_DIR)
        self.assertEqual(paths.root, indexer.DEFAULT_ARCHIVE_ROOT)
        self.assertEqual(paths.downloads, indexer.DEFAULT_DOWNLOADS_DIR)
        self.assertEqual(paths.database, indexer.DEFAULT_DATABASE_PATH)

    def test_archive_paths_are_immutable(self) -> None:
        paths = ArchivePaths.from_root(Path("C:/synthetic/archive"))

        with self.assertRaises(FrozenInstanceError):
            paths.root = Path("C:/different")  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
