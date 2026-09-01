"""Canonical bounded period and comparison semantics for owner Economics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class PeriodKind(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class EconomicsPeriod:
    kind: PeriodKind
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("period end cannot precede start")
        if self.kind is PeriodKind.DAY and self.end != self.start:
            raise ValueError("day period must contain one date")
        if self.kind is PeriodKind.WEEK and (self.end - self.start).days != 6:
            raise ValueError("week period must contain seven dates")
        if self.kind is PeriodKind.MONTH and (
            self.start.day != 1
            or self.end != _next_month(self.start) - timedelta(days=1)
        ):
            raise ValueError("month period must use calendar boundaries")
        if self.kind is PeriodKind.QUARTER and not _is_quarter(self.start, self.end):
            raise ValueError("quarter period must use calendar boundaries")
        if self.kind is PeriodKind.YEAR and (
            self.start.month != 1
            or self.start.day != 1
            or self.end != date(self.start.year, 12, 31)
        ):
            raise ValueError("year period must use calendar boundaries")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def prior_comparable(self) -> EconomicsPeriod:
        if self.kind is PeriodKind.MONTH:
            end = self.start - timedelta(days=1)
            return EconomicsPeriod(self.kind, date(end.year, end.month, 1), end)
        if self.kind is PeriodKind.QUARTER:
            end = self.start - timedelta(days=1)
            start_month = end.month - 2
            return EconomicsPeriod(self.kind, date(end.year, start_month, 1), end)
        if self.kind is PeriodKind.YEAR:
            return EconomicsPeriod(
                self.kind,
                date(self.start.year - 1, 1, 1),
                date(self.start.year - 1, 12, 31),
            )
        prior_end = self.start - timedelta(days=1)
        return EconomicsPeriod(
            self.kind, prior_end - timedelta(days=self.days - 1), prior_end
        )


def validate_comparison(
    current: EconomicsPeriod,
    prior: EconomicsPeriod,
    *,
    current_currency: str,
    prior_currency: str,
    current_policy_digest: str | None,
    prior_policy_digest: str | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if current.kind is not prior.kind or current.days != prior.days:
        blockers.append("periods_not_comparable")
    if current_currency.upper() != prior_currency.upper():
        blockers.append("currency_mismatch")
    if current_policy_digest != prior_policy_digest:
        blockers.append("policy_version_changed")
    return tuple(blockers)


def _next_month(value: date) -> date:
    return date(
        value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1
    )


def _is_quarter(start: date, end: date) -> bool:
    if start.day != 1 or start.month not in {1, 4, 7, 10}:
        return False
    month = start.month + 3
    next_quarter = date(
        start.year + (month > 12), month - 12 if month > 12 else month, 1
    )
    return end == next_quarter - timedelta(days=1)
