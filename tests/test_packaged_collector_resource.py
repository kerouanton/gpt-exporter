import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

from gpt_exporter.resources import collector_path, read_collector_source
from gpt_exporter.workflow import WorkspaceWorkflow
from gpt_exporter.workspaces import BUILTIN_WORKSPACES


class PackagedCollectorResourceTests(unittest.TestCase):
    def test_workspace_workflow_uses_packaged_collector_resource(self) -> None:
        workflow = WorkspaceWorkflow(BUILTIN_WORKSPACES.get("chatgpt"))

        self.assertEqual(workflow.provider.collector_path, collector_path())
        self.assertTrue(workflow.provider.collector_path.is_file())
        self.assertEqual(workflow.read_collector_source(), read_collector_source())


if __name__ == "__main__":
    unittest.main()
