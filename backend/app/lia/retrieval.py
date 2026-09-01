from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.beacon.service import beacon_query_service
from app.business_economics.models import EconomicsProfitabilityResultRecord
from app.customers.lia_context import customer_lia_context_service
from app.customers.models import Customer
from app.estimates.models import Estimate
from app.inventory.models import InventoryItem
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.luminary.models import LuminaryBriefingRecord
from app.operational_migration.models import HcpMigrationMasterRun
from app.payments.models import PaymentReceipt
from app.payroll.models import PayrollPayStatementRecord, PayrollReportingSnapshotRecord
from app.payroll.permissions import PayrollPermission
from app.platform.employees.models import Employee
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
        contextual_domains = ({"customers", "jobs"} & domains) if domains else set()
        contextual_reference: EvidenceReference | None = None
        if entity_id is not None and len(contextual_domains) == 1:
            domain = next(iter(contextual_domains))
            projection = (
                await customer_lia_context_service.for_customer(
                    session, context=context, customer_id=entity_id
                )
                if domain == "customers"
                else await customer_lia_context_service.for_job(
                    session, context=context, job_id=entity_id
                )
            )
            if projection is not None:
                contextual_reference = EvidenceReference(
                    domain=domain,
                    label="Minimum-necessary Customer operational context",
                    authority=projection.contract_version,
                    observed_at=projection.observed_at,
                    freshness="CURRENT_QUERY",
                    entity_id=projection.entity_id,
                    evidence_digest=projection.evidence_digest,
                    count=len(projection.jobs),
                    state=projection.safe_summary(),
                )
        # Permission checks select adapters before any protected query is executed.
        permitted = tuple(
            adapter
            for adapter in ADAPTERS
            if context.has_permission(adapter.permission)
            and (domains is None or adapter.domain in domains)
            and not (entity_id is not None and adapter.domain in contextual_domains)
        )
        observed_at = datetime.now(timezone.utc)
        evidence: list[EvidenceReference] = (
            [contextual_reference] if contextual_reference is not None else []
        )
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
        if context.has_permission(EconomicsPolicyPermission.MEASUREMENT_READ) and (
            domains is None or "business-economics" in domains
        ):
            evidence.extend(await self._economics(session, context, observed_at))
        if context.has_permission(AnalyticsPermission.READ) and (
            domains is None or "beacon" in domains
        ):
            evidence.extend(await self._beacon(session, context, observed_at))
        if context.has_permission(AdministrationPermission.COMPANY_ADMINISTER) and (
            domains is None or "migration" in domains
        ):
            evidence.extend(await self._migration(session, context, observed_at))
        if (
            context.has_permission(PayrollPermission.REPORTING_READ)
            or context.has_permission(PayrollPermission.STATEMENT_OWN_READ)
        ) and (domains is None or "payroll" in domains):
            evidence.extend(await self._payroll(session, context, observed_at))
        return tuple(evidence)

    @staticmethod
    async def _economics(
        session: AsyncSession, context: AuthorizationContext, observed_at: datetime
    ) -> tuple[EvidenceReference, ...]:
        query = (
            select(EconomicsProfitabilityResultRecord)
            .where(
                EconomicsProfitabilityResultRecord.company_id == context.company.id,
                EconomicsProfitabilityResultRecord.lifecycle == "admitted",
            )
            .order_by(
                EconomicsProfitabilityResultRecord.period_end.desc(),
                EconomicsProfitabilityResultRecord.created_at.desc(),
            )
            .limit(100)
        )
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch is not None
            else context.authorized_branch_ids
        )
        query = query.where(
            EconomicsProfitabilityResultRecord.branch_id.in_(branch_ids)
        )
        rows = tuple((await session.scalars(query)).all())
        states: dict[str, int] = {}
        for row in rows:
            quality = row.quality or row.metrics
            state = (
                "stale"
                if quality.get("freshness_status") != "current"
                else "complete"
                if quality.get("completeness_percent") == 100
                else "partial"
            )
            states[state] = states.get(state, 0) + 1
        return (
            _reference(
                domain="business-economics",
                label="Admitted profitability results",
                authority="AUTHORITATIVE_MEASUREMENT",
                observed_at=max((row.created_at for row in rows), default=observed_at),
                rows=tuple((str(row.id), row.result_digest) for row in rows),
                states=states,
            ),
        )

    @staticmethod
    async def _beacon(
        session: AsyncSession, context: AuthorizationContext, observed_at: datetime
    ) -> tuple[EvidenceReference, ...]:
        queue = await beacon_query_service.get_attention_queue(
            session, context=context, now=observed_at
        )
        signals = (*queue.active, *queue.snoozed)
        states = {
            "active": len(queue.active),
            "snoozed": len(queue.snoozed),
        }
        return (
            _reference(
                domain="beacon",
                label="Beacon attention conditions",
                authority="AUTHORITATIVE_SIGNAL_REFERENCE",
                observed_at=observed_at,
                rows=tuple((str(item.id), item.evidence_digest) for item in signals),
                states=states,
            ),
        )

    @staticmethod
    async def _migration(
        session: AsyncSession, context: AuthorizationContext, observed_at: datetime
    ) -> tuple[EvidenceReference, ...]:
        query = (
            select(HcpMigrationMasterRun)
            .where(HcpMigrationMasterRun.company_id == context.company.id)
            .order_by(HcpMigrationMasterRun.started_at.desc())
            .limit(25)
        )
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch is not None
            else context.authorized_branch_ids
        )
        query = query.where(HcpMigrationMasterRun.branch_id.in_(branch_ids))
        rows = tuple((await session.scalars(query)).all())
        states: dict[str, int] = {}
        for row in rows:
            states[row.status] = states.get(row.status, 0) + 1
        return (
            _reference(
                domain="migration",
                label="Migration authority",
                authority="AUTHORITATIVE_MIGRATION_EVIDENCE",
                observed_at=max((row.started_at for row in rows), default=observed_at),
                rows=tuple((str(row.id), row.package_digest) for row in rows),
                states=states,
            ),
        )

    @staticmethod
    async def _payroll(
        session: AsyncSession, context: AuthorizationContext, observed_at: datetime
    ) -> tuple[EvidenceReference, ...]:
        if context.has_permission(PayrollPermission.REPORTING_READ):
            reporting_rows = tuple(
                (
                    await session.scalars(
                        select(PayrollReportingSnapshotRecord)
                        .where(
                            PayrollReportingSnapshotRecord.company_id
                            == context.company.id
                        )
                        .order_by(
                            PayrollReportingSnapshotRecord.period_end.desc(),
                            PayrollReportingSnapshotRecord.created_at.desc(),
                        )
                        .limit(100)
                    )
                ).all()
            )
            reporting_states: dict[str, int] = {}
            for reporting_row in reporting_rows:
                reporting_states[reporting_row.state] = (
                    reporting_states.get(reporting_row.state, 0) + 1
                )
            return (
                _reference(
                    domain="payroll",
                    label="Payroll reporting readiness",
                    authority="AUTHORITATIVE_REPORTING_METADATA",
                    observed_at=max(
                        (row.created_at for row in reporting_rows), default=observed_at
                    ),
                    rows=tuple(
                        (str(row.id), row.report_digest) for row in reporting_rows
                    ),
                    states=reporting_states,
                ),
            )
        employee_id = await session.scalar(
            select(Employee.id).where(
                Employee.company_id == context.company.id,
                Employee.membership_id == context.membership.id,
                Employee.status == "active",
            )
        )
        if employee_id is None:
            return (
                _reference(
                    domain="payroll",
                    label="Own pay-statement availability",
                    authority="EMPLOYEE_SELF_METADATA",
                    observed_at=observed_at,
                    rows=(),
                    states={"employee_link_unavailable": 1},
                ),
            )
        statement_rows = tuple(
            (
                await session.scalars(
                    select(PayrollPayStatementRecord)
                    .where(
                        PayrollPayStatementRecord.company_id == context.company.id,
                        PayrollPayStatementRecord.employee_id == employee_id,
                        PayrollPayStatementRecord.lifecycle == "issued",
                    )
                    .order_by(PayrollPayStatementRecord.created_at.desc())
                    .limit(50)
                )
            ).all()
        )
        statement_states: dict[str, int] = {}
        for statement_row in statement_rows:
            key = f"issued:{statement_row.payment_status}:{statement_row.ytd_status}"
            statement_states[key] = statement_states.get(key, 0) + 1
        return (
            _reference(
                domain="payroll",
                label="Own pay-statement availability",
                authority="EMPLOYEE_SELF_METADATA",
                observed_at=max(
                    (row.created_at for row in statement_rows), default=observed_at
                ),
                rows=tuple(
                    (str(row.id), row.statement_digest) for row in statement_rows
                ),
                states=statement_states,
            ),
        )


def _reference(
    *,
    domain: str,
    label: str,
    authority: str,
    observed_at: datetime,
    rows: tuple[tuple[str, str], ...],
    states: dict[str, int],
) -> EvidenceReference:
    canonical = {"domain": domain, "rows": sorted(rows), "states": states}
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    state = ", ".join(f"{key}={value}" for key, value in sorted(states.items()))
    return EvidenceReference(
        domain=domain,
        label=label,
        authority=authority,
        observed_at=observed_at,
        freshness="PERSISTED_EVIDENCE" if rows else "NO_ACCEPTED_EVIDENCE",
        evidence_digest=digest,
        count=len(rows),
        state=state or "no accepted evidence",
    )


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
    if context.has_permission(
        PayrollPermission.REPORTING_READ
    ) or context.has_permission(PayrollPermission.STATEMENT_OWN_READ):
        domains.add("payroll")
    if context.has_permission(LuminaryPermission.READ):
        domains.add("luminary")
    return domains
