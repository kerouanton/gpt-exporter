from __future__ import annotations

import unittest
from datetime import datetime, timezone

from gpt_exporter.core import CanonicalConversation, CanonicalMessage
from export_provider_discord.docx_parts import docx_paths_for_parts, plan_docx_parts


def message(message_id: str, when: str) -> CanonicalMessage:
    return CanonicalMessage(
        message_id=message_id,
        role="user",
        content=message_id,
        created_at=when,
    )


def many(year: int, month: int, count: int, prefix: str) -> list[CanonicalMessage]:
    result = []
    for index in range(count):
        day = index % 28 + 1
        hour = (index // 28) % 24
        timestamp = datetime(year, month, day, hour, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        result.append(message(f"{prefix}-{index}", timestamp))
    return result


def conversation(messages: list[CanonicalMessage]) -> CanonicalConversation:
    return CanonicalConversation(
        conversation_id="discord:994497416583708703",
        provider_id="discord",
        title="Gadget MCS ↔ Littleloulita",
        messages=tuple(messages),
    )


class DiscordDocxPartTests(unittest.TestCase):
    def test_littleloulita_distribution_becomes_history_plus_quarters(self) -> None:
        messages = []
        messages += many(2022, 7, 1, "2022")
        messages += many(2025, 9, 31, "2025q3")
        messages += many(2025, 12, 5, "2025q4")
        messages += many(2026, 2, 1872, "2026q1")
        messages += many(2026, 5, 2550, "2026q2")
        messages += many(2026, 8, 2215, "2026q3")

        parts = plan_docx_parts(conversation(messages))

        self.assertEqual(
            [(part.label, part.message_count) for part in parts],
            [
                ("2022-2025", 37),
                ("2026Q1", 1872),
                ("2026Q2", 2550),
                ("2026Q3", 2215),
            ],
        )
        self.assertEqual(sum(part.message_count for part in parts), 6674)

    def test_dense_year_uses_semester_when_each_semester_is_below_threshold(self) -> None:
        messages = many(2026, 3, 700, "s1") + many(2026, 9, 700, "s2")

        parts = plan_docx_parts(conversation(messages))

        self.assertEqual(
            [(part.label, part.message_count) for part in parts],
            [("2026S1", 700), ("2026S2", 700)],
        )

    def test_sparse_single_part_keeps_unsuffixed_docx_name(self) -> None:
        parts = plan_docx_parts(conversation(many(2026, 3, 50, "small")))

        paths = docx_paths_for_parts("Discord DM A ↔ B 123.docx", parts)

        self.assertEqual([path.name for path in paths], ["Discord DM A ↔ B 123.docx"])

    def test_multipart_paths_use_period_suffixes(self) -> None:
        messages = many(2025, 12, 10, "old") + many(2026, 2, 1000, "new")
        parts = plan_docx_parts(conversation(messages))

        paths = docx_paths_for_parts("Discord DM A ↔ B 123.docx", parts)

        self.assertEqual(
            [path.name for path in paths],
            ["Discord DM A ↔ B 123 - 2025.docx", "Discord DM A ↔ B 123 - 2026Q1.docx"],
        )

    def test_undated_messages_are_never_dropped(self) -> None:
        messages = many(2026, 3, 10, "dated") + [message("undated", "")]

        parts = plan_docx_parts(conversation(messages))

        self.assertEqual(sum(part.message_count for part in parts), 11)
        self.assertEqual(parts[-1].label, "undated")


if __name__ == "__main__":
    unittest.main()
