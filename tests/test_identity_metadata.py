from __future__ import annotations

import unittest

from gpt_exporter.version import (
    APP_NAME,
    APP_SHORT_NAME,
    LEGACY_APP_NAME,
    LEGACY_DISTRIBUTION_NAME,
    LEGACY_PYTHON_PACKAGE,
    LEGACY_REPOSITORY_NAME,
    TARGET_APP_NAME,
    WINDOWS_CANONICAL_BASENAME,
    WINDOWS_LEGACY_BASENAME,
    WINDOWS_ONEDIR_NAME,
)


class IdentityMetadataTests(unittest.TestCase):
    def test_visible_product_name_is_msne(self) -> None:
        self.assertEqual(APP_NAME, "Multi Social Network Explorer")
        self.assertEqual(APP_NAME, TARGET_APP_NAME)
        self.assertNotEqual(APP_NAME, LEGACY_APP_NAME)

    def test_msne_target_identity_is_explicit(self) -> None:
        self.assertEqual(TARGET_APP_NAME, "Multi Social Network Explorer")
        self.assertEqual(APP_SHORT_NAME, "MSNE")

    def test_legacy_technical_identities_remain_explicit(self) -> None:
        self.assertEqual(LEGACY_APP_NAME, "GPT Exporter")
        self.assertEqual(LEGACY_DISTRIBUTION_NAME, "gpt-exporter")
        self.assertEqual(LEGACY_PYTHON_PACKAGE, "gpt_exporter")
        self.assertEqual(LEGACY_REPOSITORY_NAME, "gpt-exporter")

    def test_windows_executable_migration_is_staged(self) -> None:
        self.assertEqual(WINDOWS_CANONICAL_BASENAME, "MSNE")
        self.assertEqual(WINDOWS_LEGACY_BASENAME, "GPT Exporter")
        self.assertEqual(WINDOWS_ONEDIR_NAME, "GPT Exporter")
        self.assertNotEqual(WINDOWS_CANONICAL_BASENAME, WINDOWS_LEGACY_BASENAME)


if __name__ == "__main__":
    unittest.main()
