from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.estimates.models import Estimate
from app.inventory.models import InventoryItem
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.luminary.models import LuminaryBriefingRecord
from app.payments.models import PaymentReceipt
from app.payroll.permissions import PayrollPermission
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AdministrationPermission,
    AnalyticsPermission,
    CustomerPermission,
    EconomicsPolicyPermission,
    EstimatePermission,
    InventoryPermission,
    InvoicePermission,
    JobPermission,
    LuminaryPermission,
    PaymentPermission,
    PurchasingPermission,
    SchedulingPermission,
)
from app.purchasing.models import PurchaseOrder
from app.scheduling.models import Appointment

from .contracts import EvidenceReference


@dataclass(frozen=True)
class AdapterSpec:
    domain: str
    label: str
    permission: str
    model: Any
    state_column: Any


ADAPTERS = (
    AdapterSpec(
        "customers",
        "Customer records",
        CustomerPermission.READ,
        Customer,
        Customer.status,
    ),
    AdapterSpec("jobs", "Jobs", JobPermission.READ, Job, Job.status),
    AdapterSpec(
        "scheduling",
        "Appointments",
        SchedulingPermission.READ,
        Appointment,
        Appointment.status,
    ),
    AdapterSpec(
        "estimates", "Estimates", EstimatePermission.READ, Estimate, Estimate.status
    ),
    AdapterSpec(
        "invoicing", "Invoices", InvoicePermission.READ, Invoice, Invoice.status
    ),
    AdapterSpec(
        "payments",
        "Payment receipts",
        PaymentPermission.READ,
        PaymentReceipt,
        PaymentReceipt.status,
    ),
    AdapterSpec(
        "purchasing",
        "Purchase orders",
        PurchasingPermission.READ,
        PurchaseOrder,
        PurchaseOrder.status,
    ),
    AdapterSpec(
        "inventory",
        "Inventory items",
        InventoryPermission.READ,
        InventoryItem,
        InventoryItem.status,
    ),
)


class GovernedRetrievalService:
    async def retrieve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        domains: set[str] | None = None,
        entity_id: Any | None = None,
    ) -> tuple[EvidenceReference, ...]:
        # Permission checks select adapters before any protected query is executed.
        permitted = tuple(
            adapter
            for adapter in ADAPTERS
            if context.has_permission(adapter.permission)
            and (domains is None or adapter.domain in domains)
        )
        observed_at = datetime.now(timezone.utc)
        evidence: list[EvidenceReference] = []
        for adapter in permitted:
            predicates = [adapter.model.company_id == context.company.id]
            if hasattr(adapter.model, "branch_id"):
                branch_ids = (
                    frozenset({context.active_branch.id})
                    if context.active_branch is not None
                    else context.authorized_branch_ids
                )
                predicates.append(adapter.model.branch_id.in_(branch_ids))
            if entity_id is not None:
                predicates.append(adapter.model.id == entity_id)
            rows = (
                await session.execute(
                    select(adapter.state_column, func.count())
                    .where(*predicates)
                    .group_by(adapter.state_column)
                    .order_by(adapter.state_column)
                )
            ).all()
            counts = {str(state): int(count) for state, count in rows}
            total = sum(counts.values())
            canonical = {
                "company_id": str(context.company.id),
                "branch_id": str(context.active_branch.id)
                if context.active_branch
                else None,
                "domain": adapter.domain,
                "counts": counts,
            }
            digest = hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            state = (
                ", ".join(f"{key}={value}" for key, value in counts.items())
                or "no records"
            )
            evidence.append(
                EvidenceReference(
                    domain=adapter.domain,
                    label=adapter.label,
                    authority="AUTHORITATIVE_FACT",
                    observed_at=observed_at,
                    freshness="CURRENT_QUERY",
                    evidence_digest=digest,
                    count=total,
                    state=state,
                )
            )
        if context.has_permission(LuminaryPermission.READ) and (
            domains is None or "luminary" in domains
        ):
            query = (
                select(LuminaryBriefingRecord)
                .where(LuminaryBriefingRecord.company_id == context.company.id)
                .order_by(
                    LuminaryBriefingRecord.period_end.desc(),
                    LuminaryBriefingRecord.created_at.desc(),
                    LuminaryBriefingRecord.id.desc(),
                )
                .limit(1)
            )
            branch_ids = (
                frozenset({context.active_branch.id})
                if context.active_branch is not None
                else context.authorized_branch_ids
            )
            query = query.where(LuminaryBriefingRecord.branch_id.in_(branch_ids))
            if entity_id is not None:
                query = query.where(LuminaryBriefingRecord.id == entity_id)
            briefing = await session.scalar(query)
            if briefing is not None:
                evidence.append(
                    EvidenceReference(
                        domain="luminary",
                        label="Luminary owner briefing",
                        authority="AUTHORITATIVE_INTERPRETATION",
                        observed_at=briefing.generated_at,
                        freshness="PERSISTED_EVIDENCE",
                        entity_id=briefing.id,
                        evidence_digest=briefing.briefing_digest,
                        count=len(briefing.finding_ids),
                        state=briefing.completeness,
                    )
                )
        return tuple(evidence)


def permitted_domain_names(context: AuthorizationContext) -> set[str]:
    domains = {
        adapter.domain
        for adapter in ADAPTERS
        if context.has_permission(adapter.permission)
    }
    if context.has_permission(EconomicsPolicyPermission.MEASUREMENT_READ):
        domains.add("business-economics")
    if context.has_permission(AnalyticsPermission.READ):
        domains.add("beacon")
    if context.has_permission(AdministrationPermission.COMPANY_ADMINISTER):
        domains.add("migration")
    if context.has_permission(PayrollPermission.REPORTING_READ) or context.has_permission(
        PayrollPermission.STATEMENT_OWN_READ
    ):
        domains.add("payroll")
    if context.has_permission(LuminaryPermission.READ):
        domains.add("luminary")
    return domains
