import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

from gpt_exporter.legacy.model import LegacyBlock
from gpt_exporter.legacy.turns import TURN_BUILDER_VERSION, build_turns


class LegacyTurnBuilderTests(unittest.TestCase):
    def test_contiguous_same_role_blocks_merge_into_one_turn(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="question", role="user", role_confidence="medium"),
            LegacyBlock(order=5, kind="paragraph", text="answer intro", role="assistant", role_confidence="medium"),
            LegacyBlock(order=6, kind="heading", text="Analysis", role="assistant", role_confidence="low"),
            LegacyBlock(order=7, kind="table", text="A | B", role="assistant", role_confidence="low"),
        )
        turns = build_turns(blocks)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].role, "user")
        self.assertEqual(turns[1].role, "assistant")
        self.assertEqual(turns[1].block_count, 3)
        self.assertEqual(turns[1].source_orders, (5, 6, 7))
        self.assertIn("Analysis", turns[1].content)
        self.assertIn("A | B", turns[1].content)

    def test_unknown_region_is_preserved_as_turn(self) -> None:
        blocks = (
            LegacyBlock(order=1, kind="paragraph", text="user", role="user", role_confidence="medium"),
            LegacyBlock(order=2, kind="paragraph", text="ambiguous", role="unknown"),
            LegacyBlock(order=3, kind="paragraph", text="assistant", role="assistant", role_confidence="high"),
        )
        turns = build_turns(blocks)
        self.assertEqual([turn.role for turn in turns], ["user", "unknown", "assistant"])
        self.assertEqual(turns[1].confidence, "none")

    def test_hyperlink_sentinel_is_not_conversation_content(self) -> None:
        blocks = (
            LegacyBlock(order=0, kind="hyperlink_sentinel", text='HYPERLINK "https://chatgpt.com/"'),
            LegacyBlock(order=3, kind="paragraph", text="hello", role="user", role_confidence="high"),
        )
        turns = build_turns(blocks)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].content, "hello")
        self.assertNotIn(0, turns[0].source_orders)

    def test_turn_builder_version_is_explicit(self) -> None:
        self.assertEqual(TURN_BUILDER_VERSION, "legacy-turn-builder-v1")


if __name__ == "__main__":
    unittest.main()
