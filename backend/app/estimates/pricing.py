from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

CENT = Decimal("0.01")
HUNDRED = Decimal(100)
TEN_THOUSAND = Decimal(10000)


@dataclass(frozen=True, slots=True)
class PricingLine:
    key: UUID
    amount: Decimal
    taxable: bool
    rate_basis_points: int = 0
    tax_policy_id: UUID | None = None
    tax_policy_version: int | None = None


@dataclass(frozen=True, slots=True)
class PricedLine:
    key: UUID
    discount: Decimal
    basis: Decimal
    tax: Decimal
    taxable: bool
    rate_basis_points: int
    tax_policy_id: UUID | None
    tax_policy_version: int | None


@dataclass(frozen=True, slots=True)
class PricingResult:
    subtotal: Decimal
    discount: Decimal
    taxable_basis: Decimal
    tax: Decimal
    total: Decimal
    lines: tuple[PricedLine, ...]


def discount_amount(
    subtotal: Decimal, discount_type: str | None, value: Decimal | None
) -> Decimal:
    subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if discount_type is None:
        if value not in (None, Decimal(0)):
            raise ValueError("Discount value requires a discount type.")
        return Decimal("0.00")
    if discount_type not in {"fixed", "percentage"} or value is None or value < 0:
        raise ValueError("Discount is invalid.")
    if discount_type == "percentage":
        if value > HUNDRED:
            raise ValueError("Percentage discount must be between 0 and 100.")
        amount = subtotal * value / HUNDRED
    else:
        amount = value
    amount = amount.quantize(CENT, rounding=ROUND_HALF_EVEN)
    if amount > subtotal:
        raise ValueError("Discount cannot exceed the Estimate subtotal.")
    return amount


def calculate(
    lines: tuple[PricingLine, ...], discount_type: str | None, value: Decimal | None
) -> PricingResult:
    if not lines or any(line.amount < 0 for line in lines):
        raise ValueError("Pricing lines are invalid.")
    amounts = tuple(
        line.amount.quantize(CENT, rounding=ROUND_HALF_EVEN) for line in lines
    )
    subtotal = sum(amounts, Decimal("0.00"))
    discount = discount_amount(subtotal, discount_type, value)
    raw = [
        discount * amount / subtotal if subtotal else Decimal(0) for amount in amounts
    ]
    allocated = [part.quantize(CENT, rounding=ROUND_HALF_EVEN) for part in raw]
    remainder_cents = int((discount - sum(allocated, Decimal("0.00"))) / CENT)
    if remainder_cents:
        order = sorted(
            range(len(lines)),
            key=lambda index: (raw[index] - allocated[index], str(lines[index].key)),
            reverse=remainder_cents > 0,
        )
        step = CENT if remainder_cents > 0 else -CENT
        for index in order[: abs(remainder_cents)]:
            allocated[index] += step
    priced: list[PricedLine] = []
    taxable_basis = Decimal("0.00")
    tax = Decimal("0.00")
    for line, amount, allocation in zip(lines, amounts, allocated, strict=True):
        basis = amount - allocation
        line_tax = (
            (basis * Decimal(line.rate_basis_points) / TEN_THOUSAND).quantize(
                CENT, rounding=ROUND_HALF_EVEN
            )
            if line.taxable
            else Decimal("0.00")
        )
        if line.taxable:
            taxable_basis += basis
        tax += line_tax
        priced.append(
            PricedLine(
                line.key,
                allocation,
                basis,
                line_tax,
                line.taxable,
                line.rate_basis_points,
                line.tax_policy_id,
                line.tax_policy_version,
            )
        )
    total = subtotal - discount + tax
    return PricingResult(subtotal, discount, taxable_basis, tax, total, tuple(priced))
