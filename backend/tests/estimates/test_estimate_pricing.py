from decimal import Decimal
from uuid import UUID

import pytest
from app.estimates.pricing import PricingLine, calculate, discount_amount
from app.platform.permissions.catalog import permission_catalog

ONE = UUID("00000000-0000-0000-0000-000000000001")
TWO = UUID("00000000-0000-0000-0000-000000000002")


def test_fixed_discount_is_allocated_before_tax() -> None:
    result = calculate(
        (
            PricingLine(ONE, Decimal("60.00"), True, 800),
            PricingLine(TWO, Decimal("40.00"), False),
        ),
        "fixed",
        Decimal("10.00"),
    )
    assert result.subtotal == Decimal("100.00")
    assert [line.discount for line in result.lines] == [
        Decimal("6.00"),
        Decimal("4.00"),
    ]
    assert result.taxable_basis == Decimal("54.00")
    assert result.tax == Decimal("4.32")
    assert result.total == Decimal("94.32")


def test_percentage_discount_uses_half_even_and_exact_remainder() -> None:
    result = calculate(
        (
            PricingLine(ONE, Decimal("0.05"), True, 1000),
            PricingLine(TWO, Decimal("0.05"), True, 1000),
        ),
        "percentage",
        Decimal(10),
    )
    assert result.discount == Decimal("0.01")
    assert sum((line.discount for line in result.lines), Decimal(0)) == result.discount
    assert result.total == Decimal("0.09")


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("fixed", Decimal(-1)),
        ("percentage", Decimal("100.01")),
        ("unknown", Decimal(1)),
    ],
)
def test_invalid_discounts_fail_closed(kind: str, value: Decimal) -> None:
    with pytest.raises(ValueError):
        discount_amount(Decimal("10.00"), kind, value)


def test_discount_cannot_exceed_subtotal() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        discount_amount(Decimal("10.00"), "fixed", Decimal("10.01"))


def test_zero_and_maximum_discount_are_deterministic() -> None:
    assert discount_amount(Decimal("10.00"), "percentage", Decimal(0)) == Decimal(
        "0.00"
    )
    assert discount_amount(Decimal("10.00"), "percentage", Decimal(100)) == Decimal(
        "10.00"
    )


def test_estimate_permissions_are_canonical_and_separate() -> None:
    codes = {definition.code for definition in permission_catalog.definitions}
    assert "COMPANY_ESTIMATE_READ" in codes
    assert "COMPANY_ESTIMATE_MANAGE" in codes
