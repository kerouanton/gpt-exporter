import unittest

from gpt_exporter.providers.chatgpt_normalizer import _display_name


class ChatGPTToolAuthorDisplayTests(unittest.TestCase):
    def test_tool_native_names_keep_legacy_chatgpt_visible_label(self) -> None:
        self.assertEqual(_display_name("tool", "file_search"), "ChatGPT")
        self.assertEqual(_display_name("tool", "api_tool"), "ChatGPT")
        self.assertEqual(_display_name("tool", "t2uay3k.sj1i4kz"), "ChatGPT")

    def test_non_tool_native_names_are_not_collapsed(self) -> None:
        self.assertEqual(_display_name("assistant", "Custom Assistant"), "Custom Assistant")
        self.assertEqual(_display_name("user", "Bruno"), "Bruno")


if __name__ == "__main__":
    unittest.main()
