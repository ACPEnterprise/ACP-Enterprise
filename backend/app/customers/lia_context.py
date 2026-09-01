"""Minimum-necessary Customer and Job context for governed LIA retrieval."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import Estimate
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    CustomerPermission,
    EstimatePermission,
    InvoicePermission,
    JobPermission,
    ServiceAgreementPermission,
)
from app.service_agreements.models import ServiceAgreement

from .models import Customer, ServiceLocation

CONTRACT_VERSION = "CUSTOMER.LIA_CONTEXT.v1"
MAX_LOCATIONS = 10
MAX_JOBS = 10


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: UUID
    label: str
    state: str
    branch_id: UUID | None = None


class CustomerLiaContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    domain: str
    entity_id: UUID
    company_id: UUID
    branch_ids: tuple[UUID, ...]
    authorization_version: int
    display_label: str
    lifecycle_state: str
    locations: tuple[ContextItem, ...]
    jobs: tuple[ContextItem, ...]
    estimate_states: dict[str, int] | None
    invoice_states: dict[str, int] | None
    agreement_states: dict[str, int] | None
    limitations: tuple[str, ...]
    observed_at: datetime
    evidence_digest: str

    def safe_summary(self) -> str:
        components = [
            f"Customer {self.display_label} is {self.lifecycle_state}.",
            f"Authorized locations: {len(self.locations)}.",
            f"Recent authorized Jobs: {len(self.jobs)}.",
        ]
        if self.estimate_states is not None:
            components.append(f"Estimate states: {_states(self.estimate_states)}.")
        if self.invoice_states is not None:
            components.append(f"Invoice states: {_states(self.invoice_states)}.")
        if self.agreement_states is not None:
            components.append(f"Agreement states: {_states(self.agreement_states)}.")
        return " ".join(components)


class CustomerLiaContextService:
    async def for_customer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> CustomerLiaContext | None:
        if not context.has_permission(CustomerPermission.READ):
            return None
        branch_ids = _branch_ids(context)
        if not branch_ids:
            return None
        customer = await session.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.company_id == context.company.id,
                Customer.archived_at.is_(None),
                _customer_in_authorized_branch(context, branch_ids),
            )
        )
        if customer is None:
            return None
        return await self._project(
            session,
            context=context,
            customer=customer,
            branch_ids=branch_ids,
            focus_job_id=None,
        )

    async def for_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
    ) -> CustomerLiaContext | None:
        if not context.has_permission(JobPermission.READ) or not context.has_permission(
            CustomerPermission.READ
        ):
            return None
        branch_ids = _branch_ids(context)
        job = await session.scalar(
            select(Job).where(
                Job.id == job_id,
                Job.company_id == context.company.id,
                Job.branch_id.in_(branch_ids),
            )
        )
        if job is None:
            return None
        customer = await session.scalar(
            select(Customer).where(
                Customer.id == job.customer_id,
                Customer.company_id == context.company.id,
                Customer.archived_at.is_(None),
            )
        )
        if customer is None:
            return None
        return await self._project(
            session,
            context=context,
            customer=customer,
            branch_ids=branch_ids,
            focus_job_id=job.id,
        )

    async def _project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer: Customer,
        branch_ids: tuple[UUID, ...],
        focus_job_id: UUID | None,
    ) -> CustomerLiaContext:
        locations: tuple[ContextItem, ...] = ()
        jobs: tuple[ContextItem, ...] = ()
        if context.has_permission(JobPermission.READ):
            locations = tuple(
                ContextItem(
                    identity=row.id,
                    label=row.nickname or "Service location",
                    state="active",
                )
                for row in (
                    await session.scalars(
                        select(ServiceLocation)
                        .where(
                            ServiceLocation.customer_id == customer.id,
                            ServiceLocation.active.is_(True),
                            ServiceLocation.archived_at.is_(None),
                            ServiceLocation.id.in_(
                                select(Job.service_location_id).where(
                                    Job.company_id == context.company.id,
                                    Job.customer_id == customer.id,
                                    Job.branch_id.in_(branch_ids),
                                )
                            ),
                        )
                        .order_by(ServiceLocation.is_primary.desc(), ServiceLocation.id)
                        .limit(MAX_LOCATIONS)
                    )
                ).all()
            )
            job_query = (
                select(Job)
                .where(
                    Job.company_id == context.company.id,
                    Job.customer_id == customer.id,
                    Job.branch_id.in_(branch_ids),
                )
                .order_by(
                    case((Job.id == focus_job_id, 0), else_=1)
                    if focus_job_id is not None
                    else Job.updated_at.desc(),
                    Job.updated_at.desc(),
                    Job.id.desc(),
                )
                .limit(MAX_JOBS)
            )
            jobs = tuple(
                ContextItem(
                    identity=row.id,
                    label=row.job_number,
                    state=row.status,
                    branch_id=row.branch_id,
                )
                for row in (await session.scalars(job_query)).all()
            )
        estimate_states = (
            await _state_counts(session, Estimate, context, customer.id, branch_ids)
            if context.has_permission(EstimatePermission.READ)
            else None
        )
        invoice_states = (
            await _state_counts(session, Invoice, context, customer.id, branch_ids)
            if context.has_permission(InvoicePermission.READ)
            else None
        )
        agreement_states = (
            await _state_counts(
                session, ServiceAgreement, context, customer.id, branch_ids
            )
            if context.has_permission(ServiceAgreementPermission.READ)
            else None
        )
        limitations = tuple(
            name
            for permission, name in (
                (JobPermission.READ, "job_context_not_authorized"),
                (EstimatePermission.READ, "estimate_context_not_authorized"),
                (InvoicePermission.READ, "invoice_context_not_authorized"),
                (
                    ServiceAgreementPermission.READ,
                    "agreement_context_not_authorized",
                ),
            )
            if not context.has_permission(permission)
        )
        observed_at = datetime.now(timezone.utc)
        payload = {
            "contract_version": CONTRACT_VERSION,
            "domain": "jobs" if focus_job_id else "customers",
            "entity_id": str(focus_job_id or customer.id),
            "company_id": str(context.company.id),
            "branch_ids": sorted(str(item) for item in branch_ids),
            "authorization_version": context.authorization_version,
            "display_label": customer.display_name,
            "lifecycle_state": customer.status,
            "locations": [item.model_dump(mode="json") for item in locations],
            "jobs": [item.model_dump(mode="json") for item in jobs],
            "estimate_states": estimate_states,
            "invoice_states": invoice_states,
            "agreement_states": agreement_states,
            "limitations": limitations,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return CustomerLiaContext(
            domain=str(payload["domain"]),
            entity_id=focus_job_id or customer.id,
            company_id=context.company.id,
            branch_ids=branch_ids,
            authorization_version=context.authorization_version,
            display_label=customer.display_name,
            lifecycle_state=customer.status,
            locations=locations,
            jobs=jobs,
            estimate_states=estimate_states,
            invoice_states=invoice_states,
            agreement_states=agreement_states,
            limitations=limitations,
            observed_at=observed_at,
            evidence_digest=digest,
        )


async def _state_counts(
    session: AsyncSession,
    model: Any,
    context: AuthorizationContext,
    customer_id: UUID,
    branch_ids: tuple[UUID, ...],
) -> dict[str, int]:
    rows = (
        await session.execute(
            select(model.status, func.count())
            .where(
                model.company_id == context.company.id,
                model.customer_id == customer_id,
                model.branch_id.in_(branch_ids),
            )
            .group_by(model.status)
            .order_by(model.status)
        )
    ).all()
    return {str(state): int(count) for state, count in rows}


def _branch_ids(context: AuthorizationContext) -> tuple[UUID, ...]:
    if context.active_branch is not None:
        return (context.active_branch.id,)
    return tuple(sorted(context.authorized_branch_ids, key=str))


def _customer_in_authorized_branch(
    context: AuthorizationContext, branch_ids: tuple[UUID, ...]
) -> Any:
    predicates = []
    if context.has_permission(JobPermission.READ):
        predicates.append(
            exists(
                select(1).where(
                    Job.customer_id == Customer.id,
                    Job.company_id == Customer.company_id,
                    Job.branch_id.in_(branch_ids),
                )
            )
        )
    if context.has_permission(EstimatePermission.READ):
        predicates.append(
            exists(
                select(1).where(
                    Estimate.customer_id == Customer.id,
                    Estimate.company_id == Customer.company_id,
                    Estimate.branch_id.in_(branch_ids),
                )
            )
        )
    if context.has_permission(InvoicePermission.READ):
        predicates.append(
            exists(
                select(1).where(
                    Invoice.customer_id == Customer.id,
                    Invoice.company_id == Customer.company_id,
                    Invoice.branch_id.in_(branch_ids),
                )
            )
        )
    if context.has_permission(ServiceAgreementPermission.READ):
        predicates.append(
            exists(
                select(1).where(
                    ServiceAgreement.customer_id == Customer.id,
                    ServiceAgreement.company_id == Customer.company_id,
                    ServiceAgreement.branch_id.in_(branch_ids),
                )
            )
        )
    return or_(*predicates) if predicates else Customer.id.is_(None)


def _states(values: dict[str, int]) -> str:
    return (
        ", ".join(f"{key}={value}" for key, value in sorted(values.items())) or "none"
    )


customer_lia_context_service = CustomerLiaContextService()
