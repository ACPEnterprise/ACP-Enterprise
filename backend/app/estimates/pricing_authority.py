"""Membership pricing evidence and technician-adjustment authority.

The Estimate revision remains the source of the accepted amount.  This module
keeps membership and technician components explicit and reviewable instead of
collapsing them into the legacy generic discount field.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import EstimateRevision, TechnicianDiscountProposal
from app.service_agreements.models import AgreementCoverage, ServiceAgreement
from app.service_agreements.policy import policy_for_code

CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MembershipPricingEvidence:
    membership_agreement_id: UUID | None
    plan_code: str | None
    plan_version: int | None
    eligibility: str
    percentage: Decimal
    amount: Decimal
    subtotal_after_membership: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "membership_agreement_id": str(self.membership_agreement_id) if self.membership_agreement_id else None,
            "plan_code": self.plan_code,
            "plan_version": self.plan_version,
            "eligibility": self.eligibility,
            "percentage": str(self.percentage),
            "amount": str(self.amount),
            "subtotal_after_membership": str(self.subtotal_after_membership),
        }


def membership_discount(subtotal: Decimal, percentage: Decimal) -> Decimal:
    if subtotal < 0 or percentage < 0 or percentage > 100:
        raise ValueError("Membership discount inputs are invalid.")
    return (subtotal * percentage / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_EVEN)


async def active_membership_evidence(
    session: AsyncSession,
    *,
    company_id: UUID,
    customer_id: UUID,
    service_location_id: UUID | None,
    as_of: datetime | None = None,
) -> tuple[ServiceAgreement | None, MembershipPricingEvidence]:
    """Resolve only an active, date-valid, location-covered agreement.

    Unknown plan codes and missing location coverage are deliberately ineligible;
    no historical or future agreement is treated as a discount authority.
    """
    moment = (as_of or datetime.now(timezone.utc)).date()
    agreements = list((await session.scalars(
        select(ServiceAgreement).where(
            ServiceAgreement.company_id == company_id,
            ServiceAgreement.customer_id == customer_id,
            ServiceAgreement.status == "active",
            ServiceAgreement.start_date <= moment,
            ServiceAgreement.end_date >= moment,
        ).order_by(ServiceAgreement.created_at.desc())
    )).all())
    for agreement in agreements:
        if service_location_id is not None:
            covered = await session.scalar(select(AgreementCoverage.id).where(
                AgreementCoverage.company_id == company_id,
                AgreementCoverage.agreement_id == agreement.id,
                AgreementCoverage.service_location_id == service_location_id,
                AgreementCoverage.effective_from <= moment,
                AgreementCoverage.effective_to >= moment,
            ))
            if covered is None:
                continue
        code = str(agreement.plan_snapshot.get("code", "")).upper()
        policy = policy_for_code(code)
        if policy is None:
            continue
        percentage = Decimal(str(agreement.plan_snapshot.get("membership_discount_percentage", policy.discount_percentage)))
        return agreement, MembershipPricingEvidence(
            agreement.id, code, int(agreement.plan_snapshot.get("version", 1)),
            "ELIGIBLE", percentage, Decimal("0.00"), Decimal("0.00"),
        )
    return None, MembershipPricingEvidence(None, None, None, "NOT_ELIGIBLE", Decimal(0), Decimal("0.00"), Decimal("0.00"))


async def create_discount_proposal(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    estimate_id: UUID,
    revision: EstimateRevision,
    requester_user_id: UUID,
    discount_type: str,
    requested_value: Decimal,
    reason: str,
    idempotency_key: str,
    job_id: UUID | None = None,
) -> TechnicianDiscountProposal:
    if discount_type not in {"fixed", "percentage"} or requested_value < 0 or not reason.strip():
        raise ValueError("A valid discount type, value, and reason are required.")
    existing = await session.scalar(select(TechnicianDiscountProposal).where(
        TechnicianDiscountProposal.company_id == company_id,
        TechnicianDiscountProposal.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        return existing
    membership = Decimal(str(revision.calculation_evidence.get("membership_discount_amount", "0.00")))
    before = revision.total_amount
    adjustment = (before * requested_value / Decimal(100) if discount_type == "percentage" else requested_value).quantize(CENT, rounding=ROUND_HALF_EVEN)
    if adjustment > before - membership:
        raise ValueError("Technician discount exceeds the remaining customer amount.")
    proposal = TechnicianDiscountProposal(
        id=uuid4(), company_id=company_id, branch_id=branch_id,
        estimate_id=estimate_id, revision_id=revision.id, job_id=job_id,
        requester_user_id=requester_user_id, discount_type=discount_type,
        requested_value=requested_value, reason=reason.strip(), amount_before=before,
        membership_discount_amount=membership, proposed_final_amount=before - adjustment,
        state="PENDING_MANAGER_APPROVAL", idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    session.add(proposal)
    return proposal


async def decide_discount_proposal(
    session: AsyncSession, *, proposal_id: UUID, company_id: UUID,
    approver_user_id: UUID, approve: bool, reason: str | None = None,
) -> TechnicianDiscountProposal:
    proposal = await session.scalar(select(TechnicianDiscountProposal).where(
        TechnicianDiscountProposal.company_id == company_id,
        TechnicianDiscountProposal.id == proposal_id,
    ).with_for_update())
    if proposal is None:
        raise ValueError("Discount proposal was not found.")
    if proposal.requester_user_id == approver_user_id:
        raise ValueError("The requesting technician cannot approve their own discount.")
    if proposal.state != "PENDING_MANAGER_APPROVAL":
        raise ValueError("Only pending discount proposals can be decided.")
    proposal.state = "APPROVED" if approve else "REJECTED"
    if approve:
        proposal.approved_value = proposal.requested_value
        proposal.approved_amount = proposal.amount_before - proposal.proposed_final_amount
    proposal.approver_user_id = approver_user_id
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decision_reason = reason.strip() if reason else None
    return proposal
