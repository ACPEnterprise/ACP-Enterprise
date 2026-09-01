from datetime import date

import pytest
from app.business_economics.periods import (
    EconomicsPeriod,
    PeriodKind,
    validate_comparison,
)


@pytest.mark.parametrize(
    ("kind", "start", "end", "prior_start", "prior_end"),
    [
        (
            PeriodKind.DAY,
            date(2026, 9, 1),
            date(2026, 9, 1),
            date(2026, 8, 31),
            date(2026, 8, 31),
        ),
        (
            PeriodKind.WEEK,
            date(2026, 8, 24),
            date(2026, 8, 30),
            date(2026, 8, 17),
            date(2026, 8, 23),
        ),
        (
            PeriodKind.MONTH,
            date(2026, 8, 1),
            date(2026, 8, 31),
            date(2026, 7, 1),
            date(2026, 7, 31),
        ),
        (
            PeriodKind.QUARTER,
            date(2026, 7, 1),
            date(2026, 9, 30),
            date(2026, 4, 1),
            date(2026, 6, 30),
        ),
        (
            PeriodKind.YEAR,
            date(2026, 1, 1),
            date(2026, 12, 31),
            date(2025, 1, 1),
            date(2025, 12, 31),
        ),
    ],
)
def test_canonical_periods_resolve_equivalent_prior_periods(
    kind, start, end, prior_start, prior_end
) -> None:
    prior = EconomicsPeriod(kind, start, end).prior_comparable()
    assert (prior.start, prior.end) == (prior_start, prior_end)


def test_comparison_reports_policy_currency_and_period_incompatibility() -> None:
    current = EconomicsPeriod(PeriodKind.MONTH, date(2026, 8, 1), date(2026, 8, 31))
    prior = EconomicsPeriod(PeriodKind.CUSTOM, date(2026, 7, 1), date(2026, 7, 30))
    assert validate_comparison(
        current,
        prior,
        current_currency="USD",
        prior_currency="CAD",
        current_policy_digest="a",
        prior_policy_digest="b",
    ) == (
        "periods_not_comparable",
        "currency_mismatch",
        "policy_version_changed",
    )


def test_invalid_calendar_boundary_fails_closed() -> None:
    with pytest.raises(ValueError, match="calendar boundaries"):
        EconomicsPeriod(PeriodKind.MONTH, date(2026, 8, 2), date(2026, 8, 31))
