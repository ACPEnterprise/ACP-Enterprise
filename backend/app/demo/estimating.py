"""Evidence-backed, deterministic estimating for the Sales Forward Demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_economics.models import EconomicsProfitabilityResultRecord
from app.lia.contracts import EvidenceReference
from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.models import PriceBookCommercialSnapshot, PriceBookServiceItem

from .enrichment import DEMO_COMPANY_ID


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class DemoEstimateResult:
    answer: str
    evidence: tuple[EvidenceReference, ...]


def is_good_better_best_question(question: str) -> bool:
    value = question.casefold()
    return (
        "good" in value
        and "better" in value
        and "best" in value
        and "water heater" in value
    )


async def build_water_heater_estimate(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
) -> DemoEstimateResult | None:
    if context.company.id != DEMO_COMPANY_ID:
        return None
    items = list(
        (
            await session.scalars(
                select(PriceBookServiceItem).where(
                    PriceBookServiceItem.company_id == DEMO_COMPANY_ID,
                    PriceBookServiceItem.code.in_(
                        ("WH-ELECTRIC-50", "WH-ELECTRIC-50-PREM", "WH-ELECTRIC-50-PLUS")
                    ),
                    PriceBookServiceItem.status == "active",
                )
            )
        ).all()
    )
    if len(items) != 3:
        return None
    snapshots = list(
        (
            await session.scalars(
                select(PriceBookCommercialSnapshot).where(
                    PriceBookCommercialSnapshot.company_id == DEMO_COMPANY_ID,
                    PriceBookCommercialSnapshot.service_item_id.in_([item.id for item in items]),
                )
            )
        ).all()
    )
    by_code = {item.code: item for item in items}
    by_item = {snapshot.service_item_id: snapshot for snapshot in snapshots}
    if any(item.id not in by_item for item in items):
        return None
    historical_count = int(
        await session.scalar(
            select(func.count())
            .select_from(EconomicsProfitabilityResultRecord)
            .where(
                EconomicsProfitabilityResultRecord.company_id == DEMO_COMPANY_ID,
                EconomicsProfitabilityResultRecord.lifecycle == "admitted",
            )
        )
        or 0
    )
    observed_at = datetime.now(UTC)
    rows: list[str] = []
    labels = (("GOOD", "WH-ELECTRIC-50", Decimal("0.35"), "reliable standard replacement"), ("BETTER", "WH-ELECTRIC-50-PREM", Decimal("0.45"), "premium efficiency and longer warranty"), ("BEST", "WH-ELECTRIC-50-PLUS", Decimal("0.55"), "enhanced protection, expansion control, and priority warranty"))
    evidence: list[EvidenceReference] = []
    for label, code, target_margin, benefit in labels:
        snapshot = by_item[by_code[code].id]
        data = snapshot.snapshot_data
        material = Decimal(str(data.get("material_cost", "0")))
        labor = Decimal(str(data.get("labor_cost", "0")))
        equipment = Decimal(str(data.get("equipment_cost", "0")))
        overhead = Decimal(str(data.get("allocated_overhead", "0")))
        direct_cost = material + labor + equipment
        break_even = _money(direct_cost + overhead)
        target_price = _money(break_even / (Decimal("1") - target_margin))
        selling_price = _money(snapshot.unit_price)
        direct_profit = selling_price - direct_cost
        contribution = selling_price - direct_cost - overhead
        direct_margin = _money((direct_profit / selling_price) * Decimal("100")) if selling_price else Decimal("0")
        contribution_margin = _money((contribution / selling_price) * Decimal("100")) if selling_price else Decimal("0")
        rows.append(f"{label}: ${selling_price:,.2f} · {benefit}; direct cost ${direct_cost:,.2f}; break-even after allocated overhead ${break_even:,.2f}; target floor ${target_price:,.2f}; direct gross margin {direct_margin:.2f}%; contribution after overhead ${contribution:,.2f} ({contribution_margin:.2f}%).")
        evidence.append(EvidenceReference(domain="price_book", label=f"{label} Price Book snapshot", authority="SYNTHETIC_DEMO_PRICE_BOOK", observed_at=observed_at, freshness="CURRENT_QUERY", entity_id=snapshot.id, evidence_digest=snapshot.digest, count=1, state="ACTIVE", source_contract_version="sales-demo-price-book.v2", company_id=DEMO_COMPANY_ID, branch_ids=(context.active_branch.id,) if context.active_branch else (), limitations=("Synthetic demonstration data; not All County pricing.",)))
    economics_digest = "sales-demo-economics-v2".ljust(64, "0")[:64]
    evidence.append(EvidenceReference(domain="business-economics", label="Comparable completed job-cost evidence", authority="SYNTHETIC_DEMO_JOB_COST", observed_at=observed_at, freshness="CURRENT_QUERY", evidence_digest=economics_digest, count=historical_count, state="ADMITTED", source_contract_version="sales-demo-economics.v2", company_id=DEMO_COMPANY_ID, branch_ids=(context.active_branch.id,) if context.active_branch else (), limitations=("Historical averages support comparison; they are not guaranteed future costs.",)))
    answer = ("DEMO — SYNTHETIC BUSINESS DATA\n\n"
              "I found three active Price Book packages and admitted comparable job-cost evidence. "
              "Break-even includes direct material, labor, equipment, and the disclosed $120 allocated overhead method; it is not an automatically approved customer price.\n\n"
              + "\n".join(rows)
              + "\n\nThe direct gross margin is shown separately from contribution after allocated overhead. "
                "Edit scope, quantities, costs, or target margins in the draft Estimate before any external send; approval remains required. Historical evidence is synthetic and tenant-scoped.")
    return DemoEstimateResult(answer=answer, evidence=tuple(evidence))
