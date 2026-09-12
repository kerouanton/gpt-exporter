from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ProviderRemovalResilienceTests(unittest.TestCase):
    def test_canonical_engine_runs_with_gpt_provider_directory_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            source_package = REPOSITORY_ROOT / "gpt_exporter"
            target_package = temporary_root / "gpt_exporter"
            shutil.copytree(source_package, target_package)
            shutil.rmtree(target_package / "providers" / "gpt", ignore_errors=True)

            script = "\n".join(
                [
                    "import sqlite3",
                    "import tempfile",
                    "from pathlib import Path",
                    "from gpt_exporter.core.model import CanonicalConversation, CanonicalMessage",
                    "from gpt_exporter.core.serialization import write_canonical_conversation",
                    "from gpt_exporter.export.markdown import export_canonical_markdown",
                    "from gpt_exporter.index.engine import update_index",
                    "from gpt_exporter.resources import read_user_guide",
                    "root = Path(tempfile.mkdtemp()) / 'archive'",
                    "downloads = root / 'downloads'",
                    "downloads.mkdir(parents=True)",
                    "conversation = CanonicalConversation(",
                    "    conversation_id='synthetic-providerless-001',",
                    "    provider_id='synthetic',",
                    "    title='Providerless synthetic conversation',",
                    "    messages=(",
                    "        CanonicalMessage(message_id='m1', role='user', content='hello'),",
                    "        CanonicalMessage(message_id='m2', role='assistant', content='world'),",
                    "    ),",
                    ")",
                    "source = downloads / 'synthetic.json.xz'",
                    "write_canonical_conversation(source, conversation)",
                    "result = update_index(root)",
                    "assert result.success and result.updated == 1, result",
                    "with sqlite3.connect(root / 'conversations-index.sqlite') as db:",
                    "    count = db.execute(\"select count(*) from conversations where conversation_id = ?\", ('synthetic-providerless-001',)).fetchone()[0]",
                    "assert count == 1, count",
                    "markdown = root / 'synthetic.md'",
                    "export_canonical_markdown(conversation, markdown)",
                    "text = markdown.read_text(encoding='utf-8')",
                    "assert '# Providerless synthetic conversation' in text",
                    "assert '## User' in text and '## Assistant' in text",
                    "assert read_user_guide().strip()",
                    "assert not (Path(__import__('gpt_exporter').__file__).resolve().parent / 'providers' / 'gpt').exists()",
                ]
            )

            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(temporary_root)
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=temporary_root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
