from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class IndexProviderBoundaryTests(unittest.TestCase):
    def test_native_chatgpt_indexer_lives_under_provider(self) -> None:
        self.assertFalse(
            (REPOSITORY_ROOT / "gpt_exporter" / "index" / "_legacy_indexer.py").exists()
        )
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "gpt_exporter"
                / "providers"
                / "gpt"
                / "indexing"
                / "_native_indexer.py"
            ).is_file()
        )

    def test_canonical_engine_indexes_without_loading_gpt_provider(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            import tempfile
            from pathlib import Path

            from gpt_exporter.core import CanonicalConversation, CanonicalMessage
            from gpt_exporter.core.serialization import write_canonical_conversation
            from gpt_exporter.index.engine import update_index

            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root / "downloads" / "canonical.json.xz"
                write_canonical_conversation(
                    source,
                    CanonicalConversation(
                        conversation_id="canonical-boundary-001",
                        provider_id="synthetic",
                        title="Canonical boundary",
                        messages=(
                            CanonicalMessage(
                                message_id="m1",
                                role="user",
                                content="provider-neutral indexing",
                            ),
                        ),
                    ),
                )
                result = update_index(root)
                assert result.success
                assert result.updated == 1
                assert not any(
                    name == "gpt_exporter.providers.gpt"
                    or name.startswith("gpt_exporter.providers.gpt.")
                    for name in sys.modules
                )
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
