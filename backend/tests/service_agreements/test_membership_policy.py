from decimal import Decimal

import pytest

from app.service_agreements.policy import (
    DiscountApprovalState,
    policy_for_code,
    waterfall,
)


def test_all_county_membership_policy_rates_and_entitlements_are_centralized():
    assert policy_for_code("essential").discount_percentage == Decimal("10")
    assert policy_for_code("PLUS").dispatch_priority == "24_HOUR_PRIORITY"
    assert policy_for_code("PREMIER").after_hours_fee_waived is True


def test_membership_waterfall_preserves_price_book_and_requires_approval_for_additional():
    with pytest.raises(ValueError, match="Manager approval"):
        waterfall(Decimal("100.00"), Decimal("10"), "fixed", Decimal("5"))
    result = waterfall(
        Decimal("100.00"), Decimal("10"), "fixed", Decimal("5"), DiscountApprovalState.APPROVED
    )
    assert result == {
        "price_book_amount": Decimal("100.00"),
        "membership_discount_amount": Decimal("10.00"),
        "after_membership_amount": Decimal("90.00"),
        "additional_discount_amount": Decimal("5.00"),
        "final_amount": Decimal("85.00"),
    }


def test_unrecognized_plan_does_not_infer_membership_policy():
    assert policy_for_code("UNKNOWN") is None
