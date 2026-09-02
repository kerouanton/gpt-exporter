import unittest

from gpt_exporter.providers.chatgpt_normalizer import _display_name


class ChatGPTToolAuthorDisplayTests(unittest.TestCase):
    def test_visible_assistant_role_wins_over_native_tool_name(self) -> None:
        self.assertEqual(_display_name("assistant", "file_search"), "ChatGPT")
        self.assertEqual(_display_name("assistant", "api_tool"), "ChatGPT")
        self.assertEqual(_display_name("assistant", "t2uay3k.sj1i4kz"), "ChatGPT")

    def test_visible_user_role_keeps_legacy_label(self) -> None:
        self.assertEqual(_display_name("user", "Bruno"), "Bruno")
        self.assertEqual(_display_name("user", "internal-user-name"), "Bruno")

    def test_non_visible_roles_may_keep_native_name(self) -> None:
        self.assertEqual(_display_name("system", "Internal System"), "Internal System")


if __name__ == "__main__":
    unittest.main()
