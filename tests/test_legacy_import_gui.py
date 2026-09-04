import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import sqlite3
import tempfile
import unittest
from pathlib import Path

from legacy_import_gui import backup_database


class LegacyImportGuiTests(unittest.TestCase):
    def test_backup_database_copies_consistent_sqlite_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "index.sqlite"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                connection.execute("INSERT INTO sample (value) VALUES ('legacy')")
                connection.commit()

            backup = backup_database(database)
            self.assertIsNotNone(backup)
            assert backup is not None
            self.assertTrue(backup.is_file())
            self.assertNotEqual(backup, database)

            with sqlite3.connect(backup) as connection:
                value = connection.execute("SELECT value FROM sample").fetchone()[0]
            self.assertEqual(value, "legacy")

    def test_backup_database_returns_none_for_new_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "missing.sqlite"
            self.assertIsNone(backup_database(database))
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
