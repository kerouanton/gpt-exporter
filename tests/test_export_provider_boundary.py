from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ExportProviderBoundaryTests(unittest.TestCase):
    def test_native_chatgpt_markdown_renderer_lives_under_provider(self) -> None:
        self.assertFalse(
            (REPOSITORY_ROOT / "gpt_exporter" / "export" / "_legacy_markdown.py").exists()
        )
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "gpt_exporter"
                / "providers"
                / "gpt"
                / "export"
                / "_native_markdown.py"
            ).is_file()
        )

    def test_canonical_markdown_export_does_not_load_gpt_provider(self) -> None:
        script = textwrap.dedent(
            """
            import sys
            import tempfile
            from pathlib import Path

            from gpt_exporter.core import CanonicalConversation, CanonicalMessage
            from gpt_exporter.export.markdown import export_canonical_markdown

            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "conversation.md"
                result = export_canonical_markdown(
                    CanonicalConversation(
                        conversation_id="canonical-export-001",
                        provider_id="synthetic",
                        title="Canonical export",
                        messages=(
                            CanonicalMessage(
                                message_id="m1",
                                role="user",
                                content="Provider-neutral question",
                            ),
                            CanonicalMessage(
                                message_id="m2",
                                role="assistant",
                                content="Provider-neutral answer",
                            ),
                        ),
                    ),
                    output,
                )
                assert result.exported_messages == 2
                text = output.read_text(encoding="utf-8")
                assert "# Canonical export" in text
                assert "## User" in text
                assert "## Assistant" in text
                assert "Provider-neutral answer" in text
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
