from __future__ import annotations

import json
import lzma
import tempfile
import unittest
from pathlib import Path

from gpt_exporter.core import CanonicalConversation, ConversationProvider
from gpt_exporter.providers.gpt import ChatGPTProvider


class ProviderArchitectureTests(unittest.TestCase):
    def test_core_never_imports_concrete_provider_namespace(self) -> None:
        core_root = Path(__file__).resolve().parents[1] / "gpt_exporter" / "core"
        forbidden = (
            "gpt_exporter.providers",
            "from ..providers",
            "from .providers",
            "import providers",
        )
        for path in core_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, text, f"core must not depend on providers: {path}")

    def test_chatgpt_provider_satisfies_provider_contract(self) -> None:
        provider = ChatGPTProvider()
        self.assertIsInstance(provider, ConversationProvider)
        self.assertEqual(provider.descriptor.provider_id, "gpt")

    def test_chatgpt_provider_normalizes_json_xz_to_canonical_model(self) -> None:
        payload = {
            "conversation_id": "conversation-1",
            "title": "Synthetic ChatGPT conversation",
            "create_time": 1,
            "update_time": 2,
            "default_model_slug": "synthetic-model",
            "mapping": {
                "u": {
                    "message": {
                        "id": "user-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": ["hello"]},
                        "metadata": {},
                    }
                },
                "a": {
                    "message": {
                        "id": "assistant-1",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "text", "parts": ["world"]},
                        "metadata": {},
                    }
                },
                "hidden": {
                    "message": {
                        "id": "hidden-1",
                        "author": {"role": "assistant"},
                        "content": {"content_type": "thoughts", "parts": ["secret"]},
                        "metadata": {},
                    }
                },
            },
        }

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conversation.json.xz"
            with lzma.open(path, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle)
            result = ChatGPTProvider().normalize(path)

        self.assertIsInstance(result, CanonicalConversation)
        self.assertEqual(result.provider_id, "gpt")
        self.assertEqual(result.conversation_id, "conversation-1")
        self.assertEqual([message.role for message in result.messages], ["user", "assistant"])
        self.assertEqual([message.content for message in result.messages], ["hello", "world"])
        self.assertEqual(result.metadata["default_model_slug"], "synthetic-model")

    def test_core_package_imports_without_loading_gpt_provider(self) -> None:
        import sys
        import gpt_exporter.core  # noqa: F401

        self.assertNotIn("gpt_exporter.providers.gpt", sys.modules)
        self.assertNotIn("gpt_exporter.providers.gpt.provider", sys.modules)


if __name__ == "__main__":
    unittest.main()
