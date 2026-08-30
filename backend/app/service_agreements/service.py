import hashlib
import json
from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.service_agreements.models import (
    AgreementBillingOccurrence,
    AgreementCoverage,
    AgreementLifecycleEvidence,
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
    async def _evidence(
        self,
        s,
        company,
        key,
        action,
        request,
        row,
        actor,
        prior,
        resulting,
        entitlement=None,
        payload=None,
    ):
        request_digest = digest(request)
        existing = await s.scalar(
            select(AgreementLifecycleEvidence).where(
                AgreementLifecycleEvidence.company_id == company,
                AgreementLifecycleEvidence.idempotency_key == key,
            )
        )
        if existing:
            if existing.action != action or existing.request_digest != request_digest:
                raise AgreementConflict(
                    "Idempotency key conflicts with prior lifecycle evidence."
                )
            return existing
        evidence = AgreementLifecycleEvidence(
            company_id=company,
            branch_id=row.branch_id,
            agreement_id=row.id,
            entitlement_id=entitlement.id if entitlement else None,
            action=action,
            prior_status=prior,
            resulting_status=resulting,
            request_digest=request_digest,
            evidence_digest=digest(
                {
                    "request": request_digest,
                    "agreement": row.evidence_digest,
                    "result": resulting,
                }
            ),
            idempotency_key=key,
            actor_user_id=actor,
            payload=payload or {},
        )
        s.add(evidence)
        BusinessEventService.stage(
            s,
            BusinessEventCreate(
                event_type=EventType.SERVICE_ENTITLEMENT_CHANGED
                if entitlement
                else EventType.SERVICE_AGREEMENT_CHANGED,
                entity_type="service_entitlement"
                if entitlement
                else "service_agreement",
                entity_id=entitlement.id if entitlement else row.id,
                company_id=company,
                branch_id=row.branch_id,
                user_id=actor,
                payload={
                    "schema_version": "1.0",
                    "action": action,
                    "evidence_digest": evidence.evidence_digest,
                    "agreement_id": str(row.id),
                },
            ),
        )
        return None

    async def create_plan(
        self, s: AsyncSession, company: UUID, actor: UUID, p: PlanCreate
    ):
        raw = p.model_dump()
        replay = await s.scalar(
            select(AgreementPlan).where(
                AgreementPlan.company_id == company,
                AgreementPlan.idempotency_key == p.idempotency_key,
            )
        )
        if replay:
            expected = digest(
                {
                    **{k: v for k, v in raw.items() if k != "idempotency_key"},
                    "version": replay.version,
                }
            )
            if replay.definition_digest != expected:
                raise AgreementConflict(
                    "Plan idempotency key conflicts with prior authority."
                )
            return replay
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
        row = AgreementPlan(
            company_id=company,
            created_by_user_id=actor,
            version=version,
            definition_digest=digest(
                {
                    **{k: v for k, v in raw.items() if k != "idempotency_key"},
                    "version": version,
                }
            ),
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
        active = list(
            (
                await s.scalars(
                    select(AgreementPlan)
                    .where(
                        AgreementPlan.company_id == company,
                        AgreementPlan.code == row.code,
                        AgreementPlan.status == "active",
                    )
                    .with_for_update()
                )
            ).all()
        )
        for predecessor in active:
            predecessor.status = "superseded"
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

    async def transition(
        self,
        s,
        company,
        agreement_id,
        expected,
        status,
        reason=None,
        key=None,
        actor=None,
    ):
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
        action = {
            "active": "activate",
            "renewal_pending": "renewal_review",
            "renewed": "renew",
            "cancelled": "cancel",
            "expired": "expire",
        }[status]
        replay = await self._evidence(
            s,
            company,
            key or f"legacy:{agreement_id}:{expected}:{status}",
            action,
            {"agreement_id": agreement_id, "status": status, "reason": reason},
            row,
            actor or row.created_by_user_id,
            row.status,
            status,
            payload={"reason": reason, "version": expected + 1},
        )
        if replay:
            return row
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

    async def mutate_entitlement(
        self,
        s,
        company,
        actor,
        entitlement_id,
        action,
        key,
        appointment_id=None,
        job_id=None,
        evidence_reference=None,
    ):
        item = await s.scalar(
            select(ServiceEntitlement)
            .where(
                ServiceEntitlement.company_id == company,
                ServiceEntitlement.id == entitlement_id,
            )
            .with_for_update()
        )
        if not item:
            raise AgreementError("Entitlement was not found.")
        agreement = await s.scalar(
            select(ServiceAgreement).where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.id == item.agreement_id,
            )
        )
        if not agreement:
            raise AgreementError("Agreement was not found.")
        resulting = {
            "schedule_link": "scheduled",
            "job_link": "scheduled",
            "consume": "completed",
            "reverse_consumption": "scheduled",
        }[action]
        replay = await self._evidence(
            s,
            company,
            key,
            action,
            {
                "entitlement": entitlement_id,
                "appointment": appointment_id,
                "job": job_id,
                "reference": evidence_reference,
            },
            agreement,
            actor,
            item.status,
            resulting,
            item,
            {
                "appointment_id": str(appointment_id) if appointment_id else None,
                "job_id": str(job_id) if job_id else None,
                "evidence_reference": evidence_reference,
            },
        )
        if replay:
            return item
        if action == "schedule_link" and (item.status != "due" or not appointment_id):
            raise AgreementConflict("Entitlement cannot be linked to that Appointment.")
        if action == "job_link" and (
            item.status not in {"due", "scheduled"} or not job_id
        ):
            raise AgreementConflict("Entitlement cannot be linked to that Job.")
        if action == "consume" and (
            item.status != "scheduled" or not item.job_id or not evidence_reference
        ):
            raise AgreementConflict(
                "Authoritative Job completion evidence is required."
            )
        if action == "reverse_consumption" and (
            item.status != "completed" or not evidence_reference
        ):
            raise AgreementConflict("Authoritative correction evidence is required.")
        if appointment_id:
            item.appointment_id = appointment_id
        if job_id:
            item.job_id = job_id
        item.status = resulting
        await s.commit()
        await s.refresh(item)
        return item

    async def billing_ready(
        self, s, company, actor, agreement_id, period_start, period_end, key
    ):
        replay = await s.scalar(
            select(AgreementBillingOccurrence).where(
                AgreementBillingOccurrence.company_id == company,
                AgreementBillingOccurrence.idempotency_key == key,
            )
        )
        if replay:
            return replay
        agreement = await s.scalar(
            select(ServiceAgreement)
            .where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.id == agreement_id,
            )
            .with_for_update()
        )
        if not agreement or agreement.status not in {"active", "renewal_pending"}:
            raise AgreementConflict("Agreement is not eligible for billing readiness.")
        cadence = agreement.plan_snapshot.get("billing_cadence")
        amount = agreement.plan_snapshot.get("price_amount")
        currency = str(agreement.plan_snapshot.get("currency", "USD"))
        status = (
            "ready"
            if cadence != "unconfigured" and amount is not None
            else "unconfigured"
        )
        row = AgreementBillingOccurrence(
            company_id=company,
            branch_id=agreement.branch_id,
            agreement_id=agreement.id,
            period_start=period_start,
            period_end=period_end,
            amount=amount,
            currency=currency,
            status=status,
            evidence_digest=digest(
                {
                    "agreement": agreement.evidence_digest,
                    "period_start": period_start,
                    "period_end": period_end,
                    "cadence": cadence,
                    "amount": amount,
                }
            ),
            idempotency_key=key,
        )
        s.add(row)
        BusinessEventService.stage(
            s,
            BusinessEventCreate(
                event_type=EventType.SERVICE_AGREEMENT_BILLING_READY,
                entity_type="service_agreement_billing_occurrence",
                entity_id=row.id,
                company_id=company,
                branch_id=agreement.branch_id,
                user_id=actor,
                payload={
                    "schema_version": "1.0",
                    "agreement_id": str(agreement.id),
                    "status": status,
                    "evidence_digest": row.evidence_digest,
                },
            ),
        )
        await s.commit()
        await s.refresh(row)
        return row

    async def renew(
        self,
        s: AsyncSession,
        company: UUID,
        actor: UUID,
        agreement_id: UUID,
        successor_plan_id: UUID,
        start_date: date,
        end_date: date,
        expected: int,
        key: str,
    ):
        predecessor = await s.scalar(
            select(ServiceAgreement)
            .where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.id == agreement_id,
            )
            .with_for_update()
        )
        if (
            not predecessor
            or predecessor.status != "renewal_pending"
            or predecessor.version != expected
        ):
            raise AgreementConflict(
                "Agreement is not eligible for renewal or is stale."
            )
        replay = await s.scalar(
            select(ServiceAgreement).where(
                ServiceAgreement.company_id == company,
                ServiceAgreement.idempotency_key == key,
            )
        )
        if replay:
            if (
                replay.predecessor_agreement_id != agreement_id
                or replay.plan_id != successor_plan_id
            ):
                raise AgreementConflict(
                    "Renewal idempotency key conflicts with prior authority."
                )
            return replay
        plan = await s.scalar(
            select(AgreementPlan).where(
                AgreementPlan.company_id == company,
                AgreementPlan.id == successor_plan_id,
                AgreementPlan.status == "active",
            )
        )
        coverage = list(
            (
                await s.scalars(
                    select(AgreementCoverage).where(
                        AgreementCoverage.company_id == company,
                        AgreementCoverage.agreement_id == agreement_id,
                    )
                )
            ).all()
        )
        if not plan or not coverage or end_date < start_date:
            raise AgreementError("Renewal evidence is invalid or incomplete.")
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
        successor = ServiceAgreement(
            company_id=company,
            branch_id=predecessor.branch_id,
            customer_id=predecessor.customer_id,
            plan_id=plan.id,
            predecessor_agreement_id=predecessor.id,
            agreement_number=f"AGR-{count:06d}",
            status="pending_activation",
            start_date=start_date,
            end_date=end_date,
            plan_snapshot=snap,
            evidence_digest=digest(
                {
                    "predecessor": predecessor.evidence_digest,
                    "plan": snap,
                    "start": start_date,
                    "end": end_date,
                }
            ),
            idempotency_key=key,
            created_by_user_id=actor,
        )
        s.add(successor)
        await s.flush()
        for old in coverage:
            s.add(
                AgreementCoverage(
                    company_id=company,
                    agreement_id=successor.id,
                    service_location_id=old.service_location_id,
                    effective_from=start_date,
                    effective_to=end_date,
                )
            )
        predecessor.status = "renewed"
        predecessor.version += 1
        predecessor.updated_at = datetime.now(timezone.utc)
        await self._evidence(
            s,
            company,
            f"{key}:predecessor",
            "renew",
            {"successor": successor.id, "plan": plan.id},
            predecessor,
            actor,
            "renewal_pending",
            "renewed",
            payload={"successor_agreement_id": str(successor.id)},
        )
        await s.commit()
        await s.refresh(successor)
        return successor

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
