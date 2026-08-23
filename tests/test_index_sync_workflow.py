import tempfile
import unittest
from pathlib import Path
from unittest import mock

import gpt_exporter_gui as gui


class IndexSyncWorkflowTests(unittest.TestCase):
    def test_gui_index_helper_uses_open_database_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            archive_root = Path(temp_name)
            database_path = archive_root / "conversations-index.sqlite"

            with mock.patch.object(
                gui,
                "update_archive_index",
                return_value=mock.sentinel.index_result,
            ) as update_index:
                result = gui.update_browser_index(database_path)

            self.assertIs(result, mock.sentinel.index_result)
            update_index.assert_called_once_with(
                archive_root.resolve(),
                downloads_dir=(archive_root / "downloads").resolve(),
                database_path=database_path.resolve(),
                progress=None,
            )


if __name__ == "__main__":
    unittest.main()
