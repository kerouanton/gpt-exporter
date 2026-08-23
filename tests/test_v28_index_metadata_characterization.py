import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import json
import lzma
import tempfile
import unittest
from pathlib import Path

import index_chatgpt_archive as indexer


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "characterization"
CONVERSATION_ID = "conv-characterization-001"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def write_xz_conversation(path: Path, fixture_name: str) -> None:
    rendered = (
        json.dumps(load_fixture(fixture_name), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    with lzma.open(path, "wb", format=lzma.FORMAT_XZ, preset=6) as handle:
        handle.write(rendered)


class V28IndexMetadataCharacterizationTests(unittest.TestCase):
    def test_incremental_reindex_preserves_manual_project_category_and_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_root = Path(temporary_directory)
            downloads = archive_root / "downloads"
            downloads.mkdir()
            database = archive_root / "conversations-index.sqlite"
            source = downloads / f"fixture_{CONVERSATION_ID}.json.xz"

            write_xz_conversation(source, "conversation_base.json")
            indexer.build_index(downloads, archive_root, database)
            first_mtime_ns = source.stat().st_mtime_ns

            indexer.add_work_project_to_conversation(
                database,
                CONVERSATION_ID,
                "Characterization Project",
            )
            indexer.add_category_to_conversation(
                database,
                CONVERSATION_ID,
                "Characterization Category",
            )
            indexer.add_tag_to_conversation(
                database,
                CONVERSATION_ID,
                "characterization-tag",
            )

            # Replace the source with a larger version of the same conversation and
            # force a deterministic later mtime so the normal incremental path sees
            # the source as changed on every supported test filesystem.
            write_xz_conversation(source, "conversation_extended.json")
            current_stat = source.stat()
            os.utime(
                source,
                ns=(current_stat.st_atime_ns, first_mtime_ns + 1_000_000_000),
            )
            indexer.build_index(downloads, archive_root, database)

            with indexer.connect_database(database) as connection:
                project_names = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT wp.name
                        FROM conversation_work_projects AS cwp
                        JOIN work_projects AS wp ON wp.project_id = cwp.project_id
                        WHERE cwp.conversation_id = ?
                        """,
                        (CONVERSATION_ID,),
                    )
                }
                category_names = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT cat.name
                        FROM conversation_categories AS cc
                        JOIN categories AS cat ON cat.category_id = cc.category_id
                        WHERE cc.conversation_id = ?
                        """,
                        (CONVERSATION_ID,),
                    )
                }
                tag_names = {
                    row["name"]
                    for row in connection.execute(
                        """
                        SELECT t.name
                        FROM conversation_tags AS ct
                        JOIN tags AS t ON t.tag_id = ct.tag_id
                        WHERE ct.conversation_id = ?
                        """,
                        (CONVERSATION_ID,),
                    )
                }
                conversation = connection.execute(
                    "SELECT title, updated_at FROM conversations WHERE conversation_id = ?",
                    (CONVERSATION_ID,),
                ).fetchone()

            self.assertEqual(project_names, {"Characterization Project"})
            self.assertEqual(category_names, {"Characterization Category"})
            self.assertEqual(tag_names, {"characterization-tag"})
            self.assertIsNotNone(conversation)
            self.assertEqual(conversation["title"], "Characterization Fixture")


if __name__ == "__main__":
    unittest.main()
