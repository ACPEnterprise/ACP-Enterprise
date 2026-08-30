import hashlib
import json
from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.service_agreements.models import (
    AgreementCoverage,
    AgreementPlan,
    ServiceAgreement,
    ServiceEntitlement,
)
from app.service_agreements.schemas import EnrollmentCreate, PlanCreate


class AgreementError(Exception):
    pass


class AgreementConflict(AgreementError):
    pass


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


class AgreementService:
    async def create_plan(
        self, s: AsyncSession, company: UUID, actor: UUID, p: PlanCreate
    ):
        version = (
            int(
                (
                    await s.scalar(
                        select(func.coalesce(func.max(AgreementPlan.version), 0)).where(
                            AgreementPlan.company_id == company,
                            AgreementPlan.code == p.code,
                        )
                    )
                )
                or 0
            )
            + 1
        )
        raw = p.model_dump()
        row = AgreementPlan(
            company_id=company,
            created_by_user_id=actor,
            version=version,
            definition_digest=digest({**raw, "version": version}),
            **raw,
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row

    async def activate_plan(self, s: AsyncSession, company: UUID, plan_id: UUID):
        row = await s.scalar(
            select(AgreementPlan)
            .where(AgreementPlan.company_id == company, AgreementPlan.id == plan_id)
            .with_for_update()
        )
        if not row:
            raise AgreementError("Plan was not found.")
        if row.status == "active":
            return row
        if row.status != "draft":
            raise AgreementConflict("Only a draft plan can be activated.")
        row.status = "active"
        row.activated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(row)
        return row

    async def list_plans(self, s, company):
        return list(
            (
                await s.scalars(
                    select(AgreementPlan)
                    .where(AgreementPlan.company_id == company)
                    .order_by(AgreementPlan.code, AgreementPlan.version.desc())
                )
            ).all()
        )

    async def enroll(
        self, s: AsyncSession, company: UUID, actor: UUID, p: EnrollmentCreate
    ):
        replay = await s.scalar(
            select(ServiceAgreement).where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.idempotency_key == p.idempotency_key,
            )
        )
        if replay:
            if replay.customer_id != p.customer_id or replay.plan_id != p.plan_id:
                raise AgreementConflict(
                    "Idempotency key conflicts with prior enrollment."
                )
            return replay
        plan = await s.scalar(
            select(AgreementPlan).where(
                AgreementPlan.company_id == company,
                AgreementPlan.id == p.plan_id,
                AgreementPlan.status == "active",
            )
        )
        customer = await s.scalar(
            select(Customer).where(
                Customer.company_id == company, Customer.id == p.customer_id
            )
        )
        locations = list(
            (
                await s.scalars(
                    select(ServiceLocation).where(
                        ServiceLocation.customer_id == p.customer_id,
                        ServiceLocation.id.in_(p.service_location_ids),
                        ServiceLocation.active.is_(True),
                    )
                )
            ).all()
        )
        if (
            not plan
            or not customer
            or len(locations) != len(set(p.service_location_ids))
            or p.end_date < p.start_date
        ):
            raise AgreementError("Enrollment evidence is invalid or incomplete.")
        count = (
            int(
                (
                    await s.scalar(
                        select(func.count())
                        .select_from(ServiceAgreement)
                        .where(ServiceAgreement.company_id == company)
                    )
                )
                or 0
            )
            + 1
        )
        snap = {
            "plan_id": str(plan.id),
            "code": plan.code,
            "name": plan.name,
            "version": plan.version,
            "currency": plan.currency,
            "price_amount": str(plan.price_amount)
            if plan.price_amount is not None
            else None,
            "billing_cadence": plan.billing_cadence,
            "included_visits": plan.included_visits,
            "benefits": plan.benefits,
            "definition_digest": plan.definition_digest,
        }
        row = ServiceAgreement(
            company_id=company,
            branch_id=p.branch_id,
            customer_id=p.customer_id,
            plan_id=p.plan_id,
            agreement_number=f"AGR-{count:06d}",
            status="pending_activation",
            start_date=p.start_date,
            end_date=p.end_date,
            plan_snapshot=snap,
            evidence_digest=digest(
                {
                    "customer": p.customer_id,
                    "locations": sorted(map(str, p.service_location_ids)),
                    "plan": snap,
                    "start": p.start_date,
                    "end": p.end_date,
                }
            ),
            idempotency_key=p.idempotency_key,
            created_by_user_id=actor,
        )
        s.add(row)
        await s.flush()
        for location in locations:
            s.add(
                AgreementCoverage(
                    company_id=company,
                    agreement_id=row.id,
                    service_location_id=location.id,
                    effective_from=p.start_date,
                    effective_to=p.end_date,
                )
            )
        await s.commit()
        await s.refresh(row)
        return row

    async def transition(self, s, company, agreement_id, expected, status, reason=None):
        row = await s.scalar(
            select(ServiceAgreement)
            .where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.id == agreement_id,
            )
            .with_for_update()
        )
        if not row:
            raise AgreementError("Agreement was not found.")
        if row.version != expected:
            raise AgreementConflict("Agreement version is stale.")
        allowed = {
            "active": {"renewal_pending", "cancelled", "expired"},
            "pending_activation": {"active", "cancelled"},
            "renewal_pending": {"renewed", "cancelled", "expired"},
        }
        if status not in allowed.get(row.status, set()):
            raise AgreementConflict("Agreement transition is not allowed.")
        row.status = status
        row.version += 1
        row.updated_at = datetime.now(timezone.utc)
        if status == "cancelled":
            row.cancellation_reason = reason or "operator_cancelled"
        if status in {"cancelled", "expired"}:
            await s.execute(
                ServiceEntitlement.__table__.update()
                .where(
                    ServiceEntitlement.agreement_id == row.id,
                    ServiceEntitlement.status == "due",
                )
                .values(status="cancelled" if status == "cancelled" else "expired")
            )
        await s.commit()
        await s.refresh(row)
        return row

    async def generate(self, s: AsyncSession, company: UUID, agreement_id: UUID):
        agreement = await s.scalar(
            select(ServiceAgreement)
            .where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.id == agreement_id,
            )
            .with_for_update()
        )
        if not agreement or agreement.status != "active":
            raise AgreementConflict(
                "Only an active Agreement can generate entitlements."
            )
        included_visits = agreement.plan_snapshot.get("included_visits", 0)
        visits = included_visits if isinstance(included_visits, int) else 0
        coverage = list(
            (
                await s.scalars(
                    select(AgreementCoverage).where(
                        AgreementCoverage.company_id == company,
                        AgreementCoverage.agreement_id == agreement.id,
                    )
                )
            ).all()
        )
        if not coverage or visits <= 0:
            return []
        for covered in coverage:
            for seq in range(1, visits + 1):
                existing = await s.scalar(
                    select(ServiceEntitlement).where(
                        ServiceEntitlement.company_id == company,
                        ServiceEntitlement.agreement_id == agreement.id,
                        ServiceEntitlement.service_location_id
                        == covered.service_location_id,
                        ServiceEntitlement.sequence == seq,
                    )
                )
                if not existing:
                    start = add_months(
                        agreement.start_date, (seq - 1) * max(1, 12 // visits)
                    )
                    end = min(
                        agreement.end_date,
                        add_months(start, max(1, 12 // visits))
                        - __import__("datetime").timedelta(days=1),
                    )
                    s.add(
                        ServiceEntitlement(
                            company_id=company,
                            branch_id=agreement.branch_id,
                            agreement_id=agreement.id,
                            service_location_id=covered.service_location_id,
                            sequence=seq,
                            eligible_from=start,
                            eligible_to=end,
                            source_digest=digest(
                                {
                                    "agreement": agreement.evidence_digest,
                                    "location": covered.service_location_id,
                                    "sequence": seq,
                                }
                            ),
                        )
                    )
        await s.commit()
        return list(
            (
                await s.scalars(
                    select(ServiceEntitlement)
                    .where(
                        ServiceEntitlement.company_id == company,
                        ServiceEntitlement.agreement_id == agreement.id,
                    )
                    .order_by(ServiceEntitlement.eligible_from)
                )
            ).all()
        )

    async def workspace(self, s, company, branches):
        agreements = list(
            (
                await s.scalars(
                    select(ServiceAgreement)
                    .where(
                        ServiceAgreement.company_id == company,
                        ServiceAgreement.branch_id.in_(branches),
                    )
                    .order_by(ServiceAgreement.updated_at.desc())
                )
            ).all()
        )
        entitlements = list(
            (
                await s.scalars(
                    select(ServiceEntitlement)
                    .where(
                        ServiceEntitlement.company_id == company,
                        ServiceEntitlement.branch_id.in_(branches),
                    )
                    .order_by(ServiceEntitlement.eligible_from)
                )
            ).all()
        )
        return agreements, entitlements


agreement_service = AgreementService()
