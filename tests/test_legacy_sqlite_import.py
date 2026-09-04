import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import hashlib
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.legacy.sqlite_import import (
    LEGACY_ORIGIN_DISPLAY,
    ensure_legacy_provenance_schema,
    import_legacy_collection,
    legacy_conversation_id,
    validate_legacy_collection,
)
from gpt_exporter.index._legacy_indexer import connect_database


class LegacySQLiteImportTests(unittest.TestCase):
    def test_validation_checks_hash_without_creating_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_root = root / "docx"
            docx_root.mkdir()
            source = docx_root / "HAM GPT 2026-04-03 Test.docx"
            source.write_bytes(b"immutable legacy docx fixture")
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = {
                "conversations": [{
                    "source_filename": source.name,
                    "source_sha256": sha,
                    "turns": [
                        {"role": "user", "content": "question"},
                        {"role": "assistant", "content": "answer"},
                    ],
                }]
            }
            counts = validate_legacy_collection(payload, docx_root=docx_root)
            self.assertEqual(counts["conversations"], 1)
            self.assertEqual(counts["turns"], 2)
            self.assertFalse((root / "index.sqlite").exists())

    def test_import_indexes_user_assistant_and_unknown_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_root = root / "docx"
            docx_root.mkdir()
            source = docx_root / "HAM GPT 2026-04-03 Test.docx"
            source.write_bytes(b"immutable legacy docx fixture")
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            database = root / "index.sqlite"
            payload = {
                "schema": "gpt-exporter-legacy-turns-v1-collection",
                "source_count": 1,
                "conversations": [
                    {
                        "source_filename": source.name,
                        "source_sha256": sha,
                        "parser_version": "legacy-docx-parser-v2",
                        "title_hint": "Test",
                        "category_hint": "HAM",
                        "date_hint": "2026-04-03",
                        "starts_mid_conversation": False,
                        "role_inference_version": "legacy-role-inference-v3",
                        "turn_builder_version": "legacy-turn-builder-v1",
                        "turns": [
                            {"role": "user", "content": "question legacy"},
                            {"role": "assistant", "content": "réponse legacy"},
                            {"role": "unknown", "content": "zone ambiguë"},
                        ],
                    }
                ],
            }

            counts = import_legacy_collection(
                payload,
                database_path=database,
                docx_root=docx_root,
            )
            self.assertEqual(counts["updated"], 1)
            self.assertEqual(counts["turns"], 3)

            conversation_id = legacy_conversation_id(sha)
            with connect_database(database) as connection:
                ensure_legacy_provenance_schema(connection)
                row = connection.execute(
                    "SELECT title, source_json_path, docx_path, primary_origin_type FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                self.assertEqual(row["title"], "Test")
                self.assertEqual(Path(row["docx_path"]), source.resolve())
                self.assertEqual(row["primary_origin_type"], LEGACY_ORIGIN_DISPLAY)

                roles = [
                    item["author_role"]
                    for item in connection.execute(
                        "SELECT author_role FROM messages WHERE conversation_id = ? ORDER BY message_order",
                        (conversation_id,),
                    ).fetchall()
                ]
                self.assertEqual(roles, ["user", "assistant", "unknown"])

                provenance = connection.execute(
                    "SELECT source_type, source_sha256, parser_version, category_hint FROM legacy_conversation_sources WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                self.assertEqual(provenance["source_type"], "legacy_docx")
                self.assertEqual(provenance["source_sha256"], sha)
                self.assertEqual(provenance["parser_version"], "legacy-docx-parser-v2")
                self.assertEqual(provenance["category_hint"], "HAM")

                fts_count = connection.execute(
                    "SELECT count(*) AS n FROM messages_fts WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()["n"]
                self.assertEqual(fts_count, 3)

    def test_second_import_is_unchanged_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_root = root / "docx"
            docx_root.mkdir()
            source = docx_root / "PKI GPT 2026-04-03 Test.docx"
            source.write_bytes(b"fixture")
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = {
                "conversations": [{
                    "source_filename": source.name,
                    "source_sha256": sha,
                    "title_hint": "Test",
                    "date_hint": "2026-04-03",
                    "turns": [{"role": "user", "content": "hello"}],
                }]
            }
            database = root / "index.sqlite"
            first = import_legacy_collection(payload, database_path=database, docx_root=docx_root)
            second = import_legacy_collection(payload, database_path=database, docx_root=docx_root)
            self.assertEqual(first["updated"], 1)
            self.assertEqual(second["unchanged"], 1)

    def test_force_reimport_refreshes_origin_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_root = root / "docx"
            docx_root.mkdir()
            source = docx_root / "PKI GPT 2026-04-03 Test.docx"
            source.write_bytes(b"fixture")
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            payload = {
                "conversations": [{
                    "source_filename": source.name,
                    "source_sha256": sha,
                    "title_hint": "Test",
                    "turns": [{"role": "user", "content": "hello"}],
                }]
            }
            database = root / "index.sqlite"
            import_legacy_collection(payload, database_path=database, docx_root=docx_root)
            conversation_id = legacy_conversation_id(sha)
            with connect_database(database) as connection:
                connection.execute(
                    "UPDATE conversations SET primary_origin_type = 'standard' WHERE conversation_id = ?",
                    (conversation_id,),
                )
                connection.commit()

            import_legacy_collection(
                payload,
                database_path=database,
                docx_root=docx_root,
                force=True,
            )
            with connect_database(database) as connection:
                origin = connection.execute(
                    "SELECT primary_origin_type FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()["primary_origin_type"]
            self.assertEqual(origin, LEGACY_ORIGIN_DISPLAY)

    def test_sha_mismatch_refuses_validation_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_root = root / "docx"
            docx_root.mkdir()
            source = docx_root / "IT GPT 2026-03-27 Test.docx"
            source.write_bytes(b"fixture")
            payload = {
                "conversations": [{
                    "source_filename": source.name,
                    "source_sha256": "0" * 64,
                    "turns": [],
                }]
            }
            with self.assertRaises(ValueError):
                validate_legacy_collection(payload, docx_root=docx_root)
            with self.assertRaises(ValueError):
                import_legacy_collection(payload, database_path=root / "index.sqlite", docx_root=docx_root)


if __name__ == "__main__":
    unittest.main()
