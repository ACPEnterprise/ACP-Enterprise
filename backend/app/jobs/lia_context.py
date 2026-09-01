"""Minimum-necessary, permission-bounded Job context for LIA."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import DispatchAssignment
from app.estimates.models import Estimate, EstimateJobConversion
from app.invoicing.models import Invoice
from app.jobs.models import Job, JobAppointmentLink
from app.payments.models import PaymentReceipt, ReceiptEvent
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    CustomerPermission,
    DispatchPermission,
    EstimatePermission,
    InvoicePermission,
    JobPermission,
    PaymentPermission,
    SchedulingPermission,
)
from app.scheduling.models import Appointment

CONTRACT_VERSION = "JOB.LIA_CONTEXT.v1"
MAX_APPOINTMENTS = 10


class JobContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: UUID
    label: str
    state: str


class JobLiaContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    entity_id: UUID
    company_id: UUID
    branch_id: UUID
    authorization_version: int
    job_number: str
    lifecycle_state: str
    priority: str
    concurrency_version: int
    customer: JobContextItem | None
    service_location: JobContextItem | None
    appointments: tuple[JobContextItem, ...]
    dispatch_states: dict[str, int] | None
    estimate_origin: JobContextItem | None
    invoice_states: dict[str, int] | None
    payment_states: dict[str, int] | None
    limitations: tuple[str, ...]
    observed_at: datetime
    evidence_digest: str

    def safe_summary(self) -> str:
        parts = [
            f"Job {self.job_number} is {self.lifecycle_state} with {self.priority} priority.",
            f"Authorized appointments: {len(self.appointments)}.",
        ]
        for label, states in (
            ("Dispatch", self.dispatch_states),
            ("Invoice", self.invoice_states),
            ("Payment receipt", self.payment_states),
        ):
            if states is not None:
                value = (
                    ", ".join(f"{key}={count}" for key, count in sorted(states.items()))
                    or "none"
                )
                parts.append(f"{label} states: {value}.")
        return " ".join(parts)


class JobLiaContextService:
    async def project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
    ) -> JobLiaContext | None:
        if not context.has_permission(JobPermission.READ):
            return None
        branch_ids = (
            (context.active_branch.id,)
            if context.active_branch is not None
            else tuple(sorted(context.authorized_branch_ids, key=str))
        )
        if not branch_ids:
            return None
        job = await session.scalar(
            select(Job).where(
                Job.id == job_id,
                Job.company_id == context.company.id,
                Job.branch_id.in_(branch_ids),
            )
        )
        if job is None:
            return None

        customer = None
        location = None
        if context.has_permission(CustomerPermission.READ):
            customer_row = await session.scalar(
                select(Customer).where(
                    Customer.id == job.customer_id,
                    Customer.company_id == context.company.id,
                    Customer.archived_at.is_(None),
                )
            )
            location_row = await session.scalar(
                select(ServiceLocation).where(
                    ServiceLocation.id == job.service_location_id,
                    ServiceLocation.customer_id == job.customer_id,
                    ServiceLocation.archived_at.is_(None),
                )
            )
            if customer_row is not None:
                customer = JobContextItem(
                    identity=customer_row.id,
                    label=customer_row.display_name,
                    state=customer_row.status,
                )
            if location_row is not None:
                location = JobContextItem(
                    identity=location_row.id,
                    label=location_row.nickname or "Service location",
                    state="active" if location_row.active else "inactive",
                )

        appointments: tuple[JobContextItem, ...] = ()
        if context.has_permission(SchedulingPermission.READ):
            rows = (
                await session.execute(
                    select(Appointment, JobAppointmentLink.visit_sequence)
                    .join(
                        JobAppointmentLink,
                        JobAppointmentLink.appointment_id == Appointment.id,
                    )
                    .where(
                        JobAppointmentLink.company_id == context.company.id,
                        JobAppointmentLink.branch_id == job.branch_id,
                        JobAppointmentLink.job_id == job.id,
                    )
                    .order_by(JobAppointmentLink.visit_sequence, Appointment.id)
                    .limit(MAX_APPOINTMENTS)
                )
            ).all()
            appointments = tuple(
                JobContextItem(
                    identity=row.id,
                    label=f"Visit {sequence}: {row.appointment_number}",
                    state=row.status,
                )
                for row, sequence in rows
            )

        dispatch_states = (
            await _counts(
                session,
                DispatchAssignment.status,
                DispatchAssignment.company_id == context.company.id,
                DispatchAssignment.branch_id == job.branch_id,
                DispatchAssignment.job_id == job.id,
            )
            if context.has_permission(DispatchPermission.READ)
            else None
        )
        estimate_origin = None
        if context.has_permission(EstimatePermission.READ):
            conversion = await session.scalar(
                select(EstimateJobConversion).where(
                    EstimateJobConversion.company_id == context.company.id,
                    EstimateJobConversion.branch_id == job.branch_id,
                    EstimateJobConversion.job_id == job.id,
                )
            )
            if conversion is not None:
                estimate = await session.scalar(
                    select(Estimate).where(
                        Estimate.id == conversion.estimate_id,
                        Estimate.company_id == context.company.id,
                        Estimate.branch_id == job.branch_id,
                    )
                )
                if estimate is not None:
                    estimate_origin = JobContextItem(
                        identity=estimate.id,
                        label=estimate.estimate_number,
                        state=estimate.status,
                    )

        invoice_states = (
            await _counts(
                session,
                Invoice.status,
                Invoice.company_id == context.company.id,
                Invoice.branch_id == job.branch_id,
                Invoice.job_id == job.id,
            )
            if context.has_permission(InvoicePermission.READ)
            else None
        )
        payment_states = None
        if context.has_permission(PaymentPermission.READ) and context.has_permission(
            InvoicePermission.READ
        ):
            payment_states = await _counts(
                session,
                PaymentReceipt.status,
                PaymentReceipt.company_id == context.company.id,
                PaymentReceipt.branch_id == job.branch_id,
                PaymentReceipt.id.in_(
                    select(ReceiptEvent.receipt_id).where(
                        ReceiptEvent.company_id == context.company.id,
                        ReceiptEvent.invoice_id.in_(
                            select(Invoice.id).where(
                                Invoice.company_id == context.company.id,
                                Invoice.branch_id == job.branch_id,
                                Invoice.job_id == job.id,
                            )
                        ),
                    )
                ),
            )

        limitations = tuple(
            label
            for permission, label in (
                (CustomerPermission.READ, "customer_context_not_authorized"),
                (SchedulingPermission.READ, "scheduling_context_not_authorized"),
                (DispatchPermission.READ, "dispatch_context_not_authorized"),
                (EstimatePermission.READ, "estimate_context_not_authorized"),
                (InvoicePermission.READ, "invoice_context_not_authorized"),
                (PaymentPermission.READ, "payment_context_not_authorized"),
            )
            if not context.has_permission(permission)
        )
        observed_at = datetime.now(timezone.utc)
        payload = {
            "contract_version": CONTRACT_VERSION,
            "entity_id": str(job.id),
            "company_id": str(context.company.id),
            "branch_id": str(job.branch_id),
            "authorization_version": context.authorization_version,
            "job_number": job.job_number,
            "lifecycle_state": job.status,
            "priority": job.priority,
            "concurrency_version": job.concurrency_version,
            "customer": customer.model_dump(mode="json") if customer else None,
            "service_location": location.model_dump(mode="json") if location else None,
            "appointments": [item.model_dump(mode="json") for item in appointments],
            "dispatch_states": dispatch_states,
            "estimate_origin": estimate_origin.model_dump(mode="json")
            if estimate_origin
            else None,
            "invoice_states": invoice_states,
            "payment_states": payment_states,
            "limitations": limitations,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return JobLiaContext(
            entity_id=job.id,
            company_id=context.company.id,
            branch_id=job.branch_id,
            authorization_version=context.authorization_version,
            job_number=job.job_number,
            lifecycle_state=job.status,
            priority=job.priority,
            concurrency_version=job.concurrency_version,
            customer=customer,
            service_location=location,
            appointments=appointments,
            dispatch_states=dispatch_states,
            estimate_origin=estimate_origin,
            invoice_states=invoice_states,
            payment_states=payment_states,
            limitations=limitations,
            observed_at=observed_at,
            evidence_digest=digest,
        )


async def _counts(
    session: AsyncSession, state_column: Any, *predicates: Any
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(state_column, func.count())
            .where(*predicates)
            .group_by(state_column)
            .order_by(state_column)
        )
    ).all()
    return {str(state): int(count) for state, count in rows}


job_lia_context_service = JobLiaContextService()
