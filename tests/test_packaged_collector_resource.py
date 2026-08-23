import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

import archive_gui_workflow as workflow
from gpt_exporter.resources import collector_path, read_collector_source


class PackagedCollectorResourceTests(unittest.TestCase):
    def test_gui_workflow_uses_packaged_collector_resource(self) -> None:
        self.assertEqual(workflow.COLLECTOR_PATH, collector_path())
        self.assertTrue(workflow.COLLECTOR_PATH.is_file())
        self.assertEqual(workflow.read_collector_source(), read_collector_source())


if __name__ == "__main__":
    unittest.main()
