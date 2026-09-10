"""Plan deterministic time-based DOCX parts for Discord conversations."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Iterable

from gpt_exporter.core import CanonicalConversation, CanonicalMessage


DEFAULT_DENSITY_THRESHOLD = 1000


@dataclass(frozen=True, slots=True)
class DiscordDocxPart:
    """One rendered DOCX period backed by a subset of canonical messages."""

    label: str
    messages: tuple[CanonicalMessage, ...]

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def created_at(self) -> str | None:
        return self.messages[0].created_at if self.messages else None

    @property
    def updated_at(self) -> str | None:
        return self.messages[-1].created_at if self.messages else None


def _message_datetime(message: CanonicalMessage) -> datetime | None:
    value = str(message.created_at or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _year(message: CanonicalMessage) -> int | None:
    parsed = _message_datetime(message)
    return parsed.year if parsed is not None else None


def _semester(month: int) -> int:
    return 1 if month <= 6 else 2


def _quarter(month: int) -> int:
    return (month - 1) // 3 + 1


def _dense_year_labels(
    year: int,
    messages: Iterable[CanonicalMessage],
    *,
    threshold: int,
) -> dict[str, list[CanonicalMessage]]:
    by_semester: dict[int, list[CanonicalMessage]] = defaultdict(list)
    for message in messages:
        parsed = _message_datetime(message)
        if parsed is not None:
            by_semester[_semester(parsed.month)].append(message)

    result: dict[str, list[CanonicalMessage]] = {}
    for semester in (1, 2):
        semester_messages = by_semester.get(semester, [])
        if not semester_messages:
            continue
        if len(semester_messages) < threshold:
            result[f"{year}S{semester}"] = semester_messages
            continue

        by_quarter: dict[int, list[CanonicalMessage]] = defaultdict(list)
        for message in semester_messages:
            parsed = _message_datetime(message)
            assert parsed is not None
            by_quarter[_quarter(parsed.month)].append(message)
        for quarter in sorted(by_quarter):
            result[f"{year}Q{quarter}"] = by_quarter[quarter]
    return result


def plan_docx_parts(
    conversation: CanonicalConversation,
    *,
    threshold: int = DEFAULT_DENSITY_THRESHOLD,
) -> tuple[DiscordDocxPart, ...]:
    """Split a conversation using year -> semester -> quarter density rules.

    Sparse years before the first dense year are merged into one historical
    range (for example ``2022-2025``). A year is dense at ``threshold``
    messages, matching the user's photo-archive policy. Dense years are split
    by semester when possible and by quarter when a semester is itself dense.
    Messages with no parseable timestamp are preserved in an ``undated`` part.
    """

    if threshold < 1:
        raise ValueError("threshold must be at least 1")

    dated_by_year: dict[int, list[CanonicalMessage]] = defaultdict(list)
    undated: list[CanonicalMessage] = []
    for message in conversation.messages:
        year = _year(message)
        if year is None:
            undated.append(message)
        else:
            dated_by_year[year].append(message)

    if not dated_by_year:
        return (DiscordDocxPart("undated", tuple(undated)),) if undated else ()

    years = sorted(dated_by_year)
    year_counts = Counter({year: len(dated_by_year[year]) for year in years})
    dense_years = [year for year in years if year_counts[year] >= threshold]
    first_dense_year = min(dense_years) if dense_years else None

    parts: list[DiscordDocxPart] = []

    historical_years = [
        year
        for year in years
        if year_counts[year] < threshold
        and (first_dense_year is None or year < first_dense_year)
    ]
    if historical_years:
        historical_messages = tuple(
            message
            for message in conversation.messages
            if _year(message) in set(historical_years)
        )
        start_year = historical_years[0]
        end_year = historical_years[-1]
        label = str(start_year) if start_year == end_year else f"{start_year}-{end_year}"
        parts.append(DiscordDocxPart(label, historical_messages))

    for year in years:
        if year in historical_years:
            continue
        messages = dated_by_year[year]
        if len(messages) < threshold:
            parts.append(DiscordDocxPart(str(year), tuple(messages)))
            continue
        for label, selected in _dense_year_labels(year, messages, threshold=threshold).items():
            parts.append(DiscordDocxPart(label, tuple(selected)))

    if undated:
        parts.append(DiscordDocxPart("undated", tuple(undated)))

    return tuple(part for part in parts if part.messages)


def conversation_for_part(
    conversation: CanonicalConversation,
    part: DiscordDocxPart,
) -> CanonicalConversation:
    """Return a render-only canonical view for one DOCX part."""

    return replace(
        conversation,
        messages=part.messages,
        created_at=part.created_at,
        updated_at=part.updated_at,
    )


def docx_paths_for_parts(
    base_path: Path,
    parts: tuple[DiscordDocxPart, ...],
) -> tuple[Path, ...]:
    """Keep the legacy filename for one part; suffix every part when split."""

    base_path = Path(base_path)
    if len(parts) <= 1:
        return (base_path,) if parts else ()
    return tuple(base_path.with_name(f"{base_path.stem} - {part.label}.docx") for part in parts)


__all__ = [
    "DEFAULT_DENSITY_THRESHOLD",
    "DiscordDocxPart",
    "conversation_for_part",
    "docx_paths_for_parts",
    "plan_docx_parts",
]
