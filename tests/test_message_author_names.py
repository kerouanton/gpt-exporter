import gc
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from gpt_exporter.index.canonical import index_canonical_conversation
from gpt_exporter.index.storage import SCHEMA_VERSION, connect_database
from gpt_exporter.ui.browser import archive_core


class MessageAuthorNameTests(unittest.TestCase):
    def test_canonical_author_name_is_indexed_and_used_by_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            database = root / "conversations-index.sqlite"
            source = root / "conversation.json.xz"
            source.write_bytes(b"placeholder")

            conversation = CanonicalConversation(
                conversation_id="discord:1467602455704371264",
                provider_id="discord",
                title="@a33z",
                messages=(
                    CanonicalMessage(
                        message_id="1",
                        role="unknown",
                        author_id="peer",
                        author_name="a33z",
                        content="Hello",
                    ),
                    CanonicalMessage(
                        message_id="2",
                        role="user",
                        author_id="self",
                        author_name="Gadget MCS",
                        content="Coucou",
                    ),
                ),
                metadata={"origin_type": "Direct Messages"},
            )

            connection = connect_database(database)
            try:
                self.assertEqual(
                    connection.execute("PRAGMA user_version").fetchone()[0],
                    SCHEMA_VERSION,
                )
                index_canonical_conversation(
                    connection,
                    conversation,
                    source_path=source,
                    archive_root=root,
                    force=True,
                )
                rows = connection.execute(
                    "SELECT author_role, author_name FROM messages ORDER BY message_order"
                ).fetchall()
                self.assertEqual(rows[0]["author_role"], "unknown")
                self.assertEqual(rows[0]["author_name"], "a33z")
                self.assertEqual(rows[1]["author_role"], "user")
                self.assertEqual(rows[1]["author_name"], "Gadget MCS")
            finally:
                connection.close()

            excerpts = archive_core.matching_message_excerpts(
                database,
                conversation.conversation_id,
                "",
                limit=8,
            )
            self.assertEqual(excerpts[0]["author_role"], "a33z")
            self.assertEqual(excerpts[1]["author_role"], "Gadget MCS")
            # sqlite3.Connection context managers commit/rollback but do not
            # explicitly close. Force finalization before TemporaryDirectory
            # cleanup on Windows, where an open SQLite handle blocks unlink.
            gc.collect()


if __name__ == "__main__":
    unittest.main()
