"""Centralized membership policy and discount waterfall authority.

This module is deliberately provider-neutral.  It does not activate plans,
approve discounts, or move money; callers must supply authoritative agreement
state and an explicit manager approval for any additional technician discount.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum


class DiscountApprovalState(str, Enum):
    NONE = "NONE"
    PROPOSED = "PROPOSED"
    PENDING_MANAGER_APPROVAL = "PENDING_MANAGER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class MembershipPolicy:
    code: str
    discount_percentage: Decimal
    dispatch_priority: str
    after_hours_fee_waived: bool
    transferable: bool


MEMBERSHIP_POLICIES: dict[str, MembershipPolicy] = {
    "ESSENTIAL": MembershipPolicy("ESSENTIAL", Decimal(10), "48_HOUR_PRIORITY", False, False),
    "PLUS": MembershipPolicy("PLUS", Decimal(15), "24_HOUR_PRIORITY", True, True),
    "PREMIER": MembershipPolicy("PREMIER", Decimal(20), "SAME_DAY_PRIORITY_CONCIERGE", True, True),
}


def policy_for_code(code: str) -> MembershipPolicy | None:
    return MEMBERSHIP_POLICIES.get(code.strip().upper())


def discount_amount(base: Decimal, percentage: Decimal) -> Decimal:
    if base < 0 or percentage < 0 or percentage > 100:
        raise ValueError("Membership discount inputs are invalid.")
    return (base * percentage / Decimal(100)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )


def waterfall(
    price_book_amount: Decimal,
    membership_percentage: Decimal = Decimal(0),
    additional_type: str | None = None,
    additional_value: Decimal | None = None,
    approval: DiscountApprovalState = DiscountApprovalState.NONE,
) -> dict[str, Decimal | str]:
    """Return immutable pricing components without silently stacking discounts."""
    membership = discount_amount(price_book_amount, membership_percentage)
    after_membership = price_book_amount - membership
    additional = Decimal(0)
    if additional_type is not None:
        if additional_value is None or additional_value < 0:
            raise ValueError("Additional discount inputs are invalid.")
        if membership_percentage > 0 and approval is not DiscountApprovalState.APPROVED:
            raise ValueError("Manager approval is required for an additional membership discount.")
        if additional_type == "percentage":
            if additional_value > 100:
                raise ValueError("Additional percentage must be between 0 and 100.")
            additional = discount_amount(after_membership, additional_value)
        elif additional_type == "fixed":
            additional = additional_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        else:
            raise ValueError("Additional discount type is invalid.")
        if additional > after_membership:
            raise ValueError("Additional discount cannot exceed the post-membership amount.")
    return {
        "price_book_amount": price_book_amount.quantize(Decimal("0.01")),
        "membership_discount_amount": membership,
        "after_membership_amount": after_membership,
        "additional_discount_amount": additional,
        "final_amount": after_membership - additional,
    }
