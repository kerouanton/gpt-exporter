from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from gpt_exporter.index import update_index
from gpt_exporter.providers.gpt.archive.legacy_docx.promote_turns import (
    main as promote_main,
    promote_collection,
)
from gpt_exporter.providers.gpt.archive.legacy_docx.verify_cutover import verify_cutover


class CanonicalLegacyCutoverTests(unittest.TestCase):
    def test_promotion_cli_builds_default_paths(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            promote_main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_promoted_legacy_json_rebuilds_index_without_docx_sources(self) -> None:
        source_sha = "a" * 64
        legacy_payload = {
            "schema": "gpt-exporter-legacy-turns-v2-collection",
            "conversations": [
                {
                    "source_filename": "HAM GPT 2026-04-03 Synthetic.docx",
                    "source_sha256": source_sha,
                    "parser_version": "legacy-docx-parser-v3",
                    "role_inference_version": "legacy-role-inference-v3",
                    "turn_builder_version": "legacy-turn-builder-v2",
                    "title_hint": "Synthetic legacy chat",
                    "category_hint": "HAM",
                    "date_hint": "2026-04-03",
                    "starts_mid_conversation": False,
                    "turns": [
                        {"role": "user", "content": "question", "confidence": "high"},
                        {"role": "unknown", "content": "ambiguous", "confidence": "none"},
                        {"role": "assistant", "content": "answer", "confidence": "high"},
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "archive"
            downloads = archive / "downloads"
            input_path = root / "legacy-docx-turns.json"
            input_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

            result = promote_collection(input_path, downloads / "gpt" / "legacy-docx")
            self.assertEqual(result["canonical_conversations"], 1)
            self.assertEqual(result["messages"], 3)
            self.assertEqual(result["roles"], {"assistant": 1, "unknown": 1, "user": 1})

            database = archive / "conversations-index.sqlite"
            indexed = update_index(
                archive,
                downloads_dir=downloads,
                database_path=database,
                force=True,
            )
            self.assertTrue(indexed.success)
            self.assertEqual(indexed.updated, 1)

            with closing(sqlite3.connect(database)) as connection:
                conversation_id = f"legacy-docx-{source_sha}"
                row = connection.execute(
                    "SELECT title, source_json_path, docx_path FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual(row[0], "Synthetic legacy chat")
                self.assertTrue(str(row[1]).endswith(".json.xz"))
                self.assertIsNone(row[2])

                roles = connection.execute(
                    "SELECT author_role FROM messages WHERE conversation_id = ? ORDER BY message_order",
                    (conversation_id,),
                ).fetchall()
                self.assertEqual([item[0] for item in roles], ["user", "unknown", "assistant"])

                provider = connection.execute(
                    "SELECT provider_id FROM canonical_conversation_sources WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                self.assertEqual(provider[0], "gpt")

                category = connection.execute(
                    """
                    SELECT c.name
                    FROM categories c
                    JOIN conversation_categories cc ON cc.category_id = c.category_id
                    WHERE cc.conversation_id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                self.assertEqual(category[0], "HAM")

            verification = verify_cutover(
                archive,
                expected_conversations=1,
                expected_messages=3,
                expected_roles={"user": 1, "unknown": 1, "assistant": 1},
            )
            self.assertTrue(verification["success"])
            self.assertEqual(verification["docx_dependencies"], 0)
            self.assertEqual(verification["canonical_sources"], 1)

            # The whole test succeeds without ever creating a historical DOCX file.
            self.assertFalse(any(root.rglob("*.docx")))


if __name__ == "__main__":
    unittest.main()
