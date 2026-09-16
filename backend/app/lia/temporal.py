"""Deterministic resolution of bounded business periods.

Resolution is interpretation only. Domain adapters remain responsible for deciding
whether a period has authoritative meaning for their evidence.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class ResolvedTemporalContext:
    start_date: date
    end_date: date
    as_of: datetime
    timezone: str
    period_label: str
    comparison_start: date | None = None
    comparison_end: date | None = None
    comparison_label: str | None = None


MONTHS = {
    name.casefold(): index for index, name in enumerate(calendar.month_name) if name
}


def resolve_temporal_context(
    question: str,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> ResolvedTemporalContext | None:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
        timezone_name = "UTC"
    instant = now or datetime.now(UTC)
    local_now = instant.astimezone(zone)
    normalized = " ".join(question.casefold().split())

    comparison = _comparison(normalized, local_now.date())
    if comparison is not None:
        first, second = comparison
        return ResolvedTemporalContext(
            start_date=first[0],
            end_date=first[1],
            as_of=instant,
            timezone=timezone_name,
            period_label=first[2],
            comparison_start=second[0],
            comparison_end=second[1],
            comparison_label=second[2],
        )

    period = _single_period(normalized, local_now.date())
    if period is None:
        return None
    return ResolvedTemporalContext(
        start_date=period[0],
        end_date=period[1],
        as_of=instant,
        timezone=timezone_name,
        period_label=period[2],
    )


def _comparison(
    question: str, today: date
) -> tuple[tuple[date, date, str], tuple[date, date, str]] | None:
    if "this week" in question and "last week" in question:
        return (_this_week(today), _last_week(today))
    if "this month" in question and "last month" in question:
        return (_this_month(today), _last_month(today))
    month_pair = re.search(
        r"\b("
        + "|".join(MONTHS)
        + r")(?:\s+(20\d{2}))?\s+(?:vs\.?|versus|and)\s+("
        + "|".join(MONTHS)
        + r")(?:\s+(20\d{2}))?\b",
        question,
    )
    if month_pair:
        first_year = int(month_pair.group(2) or today.year)
        second_year = int(month_pair.group(4) or first_year)
        return (
            _month(first_year, MONTHS[month_pair.group(1)]),
            _month(second_year, MONTHS[month_pair.group(3)]),
        )
    return None


def _single_period(question: str, today: date) -> tuple[date, date, str] | None:
    explicit = re.search(
        r"\b(20\d{2}-\d{2}-\d{2})\s+(?:through|to)\s+(20\d{2}-\d{2}-\d{2})\b", question
    )
    if explicit:
        start, end = (
            date.fromisoformat(explicit.group(1)),
            date.fromisoformat(explicit.group(2)),
        )
        return (start, end, f"{start.isoformat()} through {end.isoformat()}")
    explicit_day = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", question)
    if explicit_day:
        value = date.fromisoformat(explicit_day.group(1))
        return (value, value, value.isoformat())
    month_range = re.search(
        r"\b("
        + "|".join(MONTHS)
        + r")\s+(?:through|to)\s+("
        + "|".join(MONTHS)
        + r")(?:\s+(20\d{2}))?\b",
        question,
    )
    if month_range:
        year = int(month_range.group(3) or today.year)
        first = _month(year, MONTHS[month_range.group(1)])
        last = _month(year, MONTHS[month_range.group(2)])
        return (first[0], last[1], f"{first[2]} through {last[2]}")
    if "tomorrow" in question:
        value = today + timedelta(days=1)
        return (value, value, "tomorrow")
    if "yesterday" in question:
        value = today - timedelta(days=1)
        return (value, value, "yesterday")
    if re.search(r"\btoday\b|\bthis morning\b|\bsince lunch\b", question):
        return (today, today, "today")
    if "last week" in question:
        return _last_week(today)
    if "this week" in question:
        return _this_week(today)
    if "last month" in question:
        return _last_month(today)
    if "this month" in question:
        return _this_month(today)
    if "last year" in question:
        return (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year")
    if "this year" in question:
        return (date(today.year, 1, 1), date(today.year, 12, 31), "this year")
    weekday = re.search(
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", question
    )
    if weekday:
        target = list(calendar.day_name).index(weekday.group(1).title())
        value = today + timedelta(days=(target - today.weekday()) % 7)
        return (value, value, weekday.group(1))
    named = re.search(r"\b(" + "|".join(MONTHS) + r")(?:\s+(20\d{2}))?\b", question)
    if named:
        return _month(int(named.group(2) or today.year), MONTHS[named.group(1)])
    return None


def _this_week(today: date) -> tuple[date, date, str]:
    start = today - timedelta(days=today.weekday())
    return (start, start + timedelta(days=6), "this week")


def _last_week(today: date) -> tuple[date, date, str]:
    start = today - timedelta(days=today.weekday() + 7)
    return (start, start + timedelta(days=6), "last week")


def _this_month(today: date) -> tuple[date, date, str]:
    return _month(today.year, today.month, "this month")


def _last_month(today: date) -> tuple[date, date, str]:
    previous = today.replace(day=1) - timedelta(days=1)
    return _month(previous.year, previous.month, "last month")


def _month(year: int, month: int, label: str | None = None) -> tuple[date, date, str]:
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return (start, end, label or start.strftime("%B %Y"))
