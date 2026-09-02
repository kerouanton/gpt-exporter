import sqlite3
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.index import initialize_normalized_database


class WorkspaceInitializationTests(unittest.TestCase):
    def test_empty_workspace_database_is_browser_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            database = Path(temp_name) / "New Archive" / "conversations-index.sqlite"

            result = initialize_normalized_database(database)

            self.assertEqual(result, database.resolve())
            self.assertTrue(database.is_file())
            connection = sqlite3.connect(database)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                    )
                }
                count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            finally:
                connection.close()

            self.assertIn("conversations", tables)
            self.assertIn("messages", tables)
            self.assertIn("conversation_providers", tables)
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
