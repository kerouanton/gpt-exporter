import unittest

import index_chatgpt_archive as indexer


class IndexerSmokeTests(unittest.TestCase):
    def test_origin_classification(self) -> None:
        self.assertEqual(indexer.classify_origin_id("g-p-example"), "project")
        self.assertEqual(indexer.classify_origin_id("g-example"), "custom_gpt")
        self.assertEqual(indexer.classify_origin_id("other"), "other")

    def test_primary_origin_standard(self) -> None:
        self.assertEqual(indexer.primary_origin([]), ("standard", None))

    def test_primary_origin_first_detected(self) -> None:
        origins = [
            {
                "origin_id": "g-p-project",
                "origin_type": "project",
                "source": "test",
            },
            {
                "origin_id": "g-custom",
                "origin_type": "custom_gpt",
                "source": "test",
            },
        ]
        self.assertEqual(indexer.primary_origin(origins), ("project", "g-p-project"))

    def test_normalize_text(self) -> None:
        self.assertEqual(indexer.normalize_text("  alpha\n beta  "), "alpha beta")
        self.assertEqual(indexer.normalize_text(["alpha", "beta"]), "alpha\nbeta")
        self.assertEqual(indexer.normalize_text({"parts": ["alpha", "beta"]}), "alpha\nbeta")

    def test_slugify(self) -> None:
        self.assertEqual(indexer.slugify("Résumé test"), "Resume_test")
        self.assertEqual(indexer.slugify("  "), "Untitled")


if __name__ == "__main__":
    unittest.main()
