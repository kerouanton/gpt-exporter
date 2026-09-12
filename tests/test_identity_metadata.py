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
)


class IdentityMetadataTests(unittest.TestCase):
    def test_phase_one_keeps_visible_legacy_name(self) -> None:
        self.assertEqual(APP_NAME, "GPT Exporter")
        self.assertEqual(APP_NAME, LEGACY_APP_NAME)

    def test_msne_target_identity_is_explicit(self) -> None:
        self.assertEqual(TARGET_APP_NAME, "Multi Social Network Explorer")
        self.assertEqual(APP_SHORT_NAME, "MSNE")

    def test_legacy_technical_identities_remain_explicit(self) -> None:
        self.assertEqual(LEGACY_DISTRIBUTION_NAME, "gpt-exporter")
        self.assertEqual(LEGACY_PYTHON_PACKAGE, "gpt_exporter")
        self.assertEqual(LEGACY_REPOSITORY_NAME, "gpt-exporter")


if __name__ == "__main__":
    unittest.main()
