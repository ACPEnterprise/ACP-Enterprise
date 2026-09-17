from decimal import Decimal

import pytest

from app.estimates.pricing_authority import membership_discount
from app.service_agreements.policy import DiscountApprovalState, waterfall


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [(Decimal(10), Decimal("10.00")), (Decimal(15), Decimal("15.00")), (Decimal(20), Decimal("20.00"))],
)
def test_membership_percentage_is_deterministic(percentage, expected):
    assert membership_discount(Decimal("100.00"), percentage) == expected


def test_membership_and_technician_components_do_not_silently_stack():
    with pytest.raises(ValueError, match="approval"):
        waterfall(Decimal("100.00"), Decimal(10), "fixed", Decimal(5))
    approved = waterfall(
        Decimal("100.00"), Decimal(10), "fixed", Decimal(5), DiscountApprovalState.APPROVED
    )
    assert approved["membership_discount_amount"] == Decimal("10.00")
    assert approved["additional_discount_amount"] == Decimal("5.00")
    assert approved["final_amount"] == Decimal("85.00")


def test_unknown_plan_is_not_a_policy():
    from app.service_agreements.policy import policy_for_code

    assert policy_for_code("UNKNOWN") is None
