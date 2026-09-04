import os
file_name = os.path.basename(__file__)
print(f"The filename of this script is: {file_name}")

import unittest

from gpt_exporter.legacy.model import LegacyBlock
from gpt_exporter.legacy.roles import infer_roles


class LegacyRoleInferenceTests(unittest.TestCase):
    def test_one_blank_assistant_anchor_stops_user_propagation(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="question", style="Normal", blank_blocks_before=3, run_count=1),
            LegacyBlock(order=5, kind="paragraph", text="Parfait — réponse", style="Normal", blank_blocks_before=1, run_count=3, bold_run_count=1),
            LegacyBlock(order=6, kind="heading", text="Analyse", style="Heading 1"),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "user")
        self.assertEqual(inferred[1].role, "assistant")
        self.assertEqual(inferred[1].role_confidence, "medium")
        self.assertEqual(inferred[2].role, "assistant")

    def test_formatted_assistant_after_strong_gap_is_assistant_anchor(self) -> None:
        blocks = (
            LegacyBlock(order=10, kind="paragraph", text="Parfait — là on voit", style="Normal", blank_blocks_before=2, run_count=3, bold_run_count=1),
            LegacyBlock(order=11, kind="heading", text="Analyse", style="Heading 1"),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "assistant")
        self.assertEqual(inferred[0].role_confidence, "high")
        self.assertEqual(inferred[1].role, "assistant")

    def test_ambiguous_strong_boundary_resets_to_unknown(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="question", style="Normal", blank_blocks_before=3, run_count=1),
            LegacyBlock(order=4, kind="paragraph", text="continuation", style="Normal", run_count=1),
            LegacyBlock(order=7, kind="paragraph", text="ambiguous", style="Normal", blank_blocks_before=2, run_count=2),
            LegacyBlock(order=8, kind="paragraph", text="more ambiguous", style="Normal", run_count=1),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "user")
        self.assertEqual(inferred[1].role, "user")
        self.assertEqual(inferred[2].role, "unknown")
        self.assertEqual(inferred[3].role, "unknown")

    def test_unresolved_weak_boundary_stops_user_region(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="question", style="Normal", blank_blocks_before=3, run_count=1),
            LegacyBlock(order=5, kind="paragraph", text="ambiguous answer opening", style="Normal", blank_blocks_before=1, run_count=1),
            LegacyBlock(order=6, kind="paragraph", text="more text", style="Normal", run_count=1),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "user")
        self.assertEqual(inferred[1].role, "unknown")
        self.assertEqual(inferred[2].role, "unknown")

    def test_plain_turn_between_assistant_anchors_can_be_user(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="Parfait — réponse", style="Normal", blank_blocks_before=3, run_count=3, bold_run_count=1),
            LegacyBlock(order=10, kind="paragraph", text="mon résultat de test", style="Normal", blank_blocks_before=1, run_count=1),
            LegacyBlock(order=12, kind="paragraph", text="Excellent — ce résultat confirme", style="Normal", blank_blocks_before=1, run_count=3, bold_run_count=1),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "assistant")
        self.assertEqual(inferred[1].role, "user")
        self.assertEqual(inferred[1].role_confidence, "medium")
        self.assertEqual(inferred[2].role, "assistant")

    def test_first_assistant_like_formatted_capture_can_start_mid_answer(self) -> None:
        blocks = (
            LegacyBlock(order=3, kind="paragraph", text="Oui — on va faire un test", style="Normal", blank_blocks_before=3, run_count=5, bold_run_count=1),
        )
        inferred = infer_roles(blocks)
        self.assertEqual(inferred[0].role, "assistant")


if __name__ == "__main__":
    unittest.main()
