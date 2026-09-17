from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import AccountingPeriod
from app.beacon.history import (
    EvaluationDisposition,
    beacon_evaluation_history_service,
)
from app.beacon.service import beacon_query_service
from app.business_economics.models import EconomicsProfitabilityResultRecord
from app.customers.lia_context import customer_lia_context_service
from app.customers.models import Customer
from app.data_quality.catalog import QUALITY_CATALOG
from app.dispatch.errors import DispatchNotFound
from app.dispatch.models import DispatchAssignment
from app.dispatch.service import dispatch_service
from app.estimates.models import Estimate
from app.financial_reporting.errors import (
    ReportingIntegrityError,
    ReportingNotFound,
    ReportingRequestError,
)
from app.financial_reporting.service import financial_reporting_service
from app.inventory.models import InventoryItem
from app.invoicing.models import Invoice
from app.jobs.lia_context import job_lia_context_service
from app.jobs.models import Job
from app.luminary.models import LuminaryBriefingRecord
from app.operational_assets.lia_context import asset_lia_context_service
from app.operational_assets.models import Asset
from app.operational_migration.models import HcpMigrationMasterRun
from app.payments.models import PaymentReceipt
from app.payroll.models import PayrollPayStatementRecord, PayrollReportingSnapshotRecord
from app.payroll.operations import PayrollOperationsService
from app.payroll.permissions import PayrollPermission
from app.platform.audit.models import AuditRecord
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AccountingPermission,
    AdministrationPermission,
    AnalyticsPermission,
    AssetPermission,
    CommunicationsPermission,
    CustomerPermission,
    DispatchPermission,
    EconomicsPolicyPermission,
    EstimatePermission,
    InventoryPermission,
    InvoicePermission,
    JobPermission,
    LaunchPlatformPermission,
    LuminaryPermission,
    PaymentPermission,
    PriceBookPermission,
    PurchasingPermission,
    SchedulingPermission,
    WorkforcePermission,
)
from app.price_book.models import PriceBookServiceItem
from app.purchasing.models import PurchaseOrder
from app.scheduling.models import Appointment
from app.timekeeping.models import PayPeriod, WorkdayTimeEntryRevision
from app.timekeeping.permissions import TimekeepingPermission
from app.workforce.lia_context import workforce_lia_context_service
from app.workforce.service import workforce_operations_service

from .contracts import EvidenceReference, LiaTemporalContext


@dataclass(frozen=True)
class AdapterSpec:
    domain: str
    label: str
    permission: str
    model: Any
    state_column: Any
    temporal_start_column: Any | None = None
    temporal_end_column: Any | None = None
    temporal_kind: str | None = None
    entity_column: Any | None = None
    entity_columns: dict[str, Any] | None = None


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
        Appointment.arrival_window_start_at,
        Appointment.arrival_window_end_at,
        "datetime_overlap",
    ),
    AdapterSpec(
        "dispatch",
        "Dispatch assignments",
        DispatchPermission.READ,
        DispatchAssignment,
        DispatchAssignment.status,
        DispatchAssignment.window_start_at,
        DispatchAssignment.window_end_at,
        "datetime_overlap",
        None,
        {
            "workforce": DispatchAssignment.primary_employee_id,
            "scheduling": DispatchAssignment.appointment_id,
            "jobs": DispatchAssignment.job_id,
        },
    ),
    AdapterSpec(
        "estimates",
        "Estimates",
        EstimatePermission.READ,
        Estimate,
        Estimate.status,
        Estimate.created_at,
        None,
        "datetime_start",
    ),
    AdapterSpec(
        "invoicing",
        "Invoices",
        InvoicePermission.READ,
        Invoice,
        Invoice.status,
        Invoice.issue_date,
        None,
        "date_start",
    ),
    AdapterSpec(
        "payments",
        "Payment receipts",
        PaymentPermission.READ,
        PaymentReceipt,
        PaymentReceipt.status,
        PaymentReceipt.captured_at,
        None,
        "datetime_start",
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
    AdapterSpec(
        "assets", "Operational Assets", AssetPermission.READ, Asset, Asset.lifecycle
    ),
    AdapterSpec(
        "timekeeping",
        "Accepted timekeeping revisions",
        TimekeepingPermission.ADMIN_READ,
        WorkdayTimeEntryRevision,
        WorkdayTimeEntryRevision.state,
        WorkdayTimeEntryRevision.work_date,
        None,
        "date_start",
        WorkdayTimeEntryRevision.employee_id,
    ),
    AdapterSpec(
        "accounting",
        "Accounting period readiness",
        AccountingPermission.REPORT_READ,
        AccountingPeriod,
        AccountingPeriod.status,
        AccountingPeriod.start_date,
        AccountingPeriod.end_date,
        "date_overlap",
    ),
    AdapterSpec(
        "price-book",
        "Price Book services",
        PriceBookPermission.READ,
        PriceBookServiceItem,
        PriceBookServiceItem.status,
    ),
    AdapterSpec(
        "audit",
        "Scoped audit outcomes",
        LaunchPlatformPermission.AUDIT_READ,
        AuditRecord,
        AuditRecord.outcome,
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
        entity_domain: str | None = None,
        temporal: LiaTemporalContext | None = None,
        requested_accounting_basis: str | None = None,
    ) -> tuple[EvidenceReference, ...]:
        observed_at = datetime.now(timezone.utc)
        contextual_domains = (
            {"customers", "jobs", "assets", "workforce"} & domains if domains else set()
        )
        contextual_reference: EvidenceReference | None = None
        dispatch_reference: EvidenceReference | None = None
        contextual_dispatch_attempted = False
        if entity_id is not None and len(contextual_domains) == 1 and temporal is None:
            domain = next(iter(contextual_domains))
            if domain == "customers":
                customer_projection = await customer_lia_context_service.for_customer(
                    session, context=context, customer_id=entity_id
                )
                if customer_projection is not None:
                    contextual_reference = EvidenceReference(
                        domain=domain,
                        label="Minimum-necessary Customer operational context",
                        authority=customer_projection.contract_version,
                        observed_at=customer_projection.observed_at,
                        freshness="CURRENT_QUERY",
                        entity_id=customer_projection.entity_id,
                        evidence_digest=customer_projection.evidence_digest,
                        count=len(customer_projection.jobs),
                        state=customer_projection.safe_summary(),
                        source_contract_version=customer_projection.contract_version,
                        company_id=customer_projection.company_id,
                        branch_ids=customer_projection.branch_ids,
                        authorization_version=customer_projection.authorization_version,
                        limitations=customer_projection.limitations,
                    )
            elif domain == "jobs":
                job_projection = await job_lia_context_service.project(
                    session, context=context, job_id=entity_id
                )
                if job_projection is not None:
                    contextual_reference = EvidenceReference(
                        domain=domain,
                        label="Minimum-necessary Job operational context",
                        authority=job_projection.contract_version,
                        observed_at=job_projection.observed_at,
                        freshness="CURRENT_QUERY",
                        entity_id=job_projection.entity_id,
                        evidence_digest=job_projection.evidence_digest,
                        count=len(job_projection.appointments),
                        state=job_projection.safe_summary(),
                        source_contract_version=job_projection.contract_version,
                        company_id=job_projection.company_id,
                        branch_ids=(job_projection.branch_id,),
                        authorization_version=job_projection.authorization_version,
                        limitations=job_projection.limitations,
                    )
            elif domain == "assets":
                asset_projection = await asset_lia_context_service.project(
                    session, context=context, asset_id=entity_id
                )
                if asset_projection is not None:
                    contextual_reference = EvidenceReference(
                        domain=domain,
                        label="Minimum-necessary Asset operational context",
                        authority=asset_projection.contract_version,
                        observed_at=asset_projection.observed_at,
                        freshness="CURRENT_QUERY",
                        entity_id=asset_projection.entity_id,
                        evidence_digest=asset_projection.evidence_digest,
                        count=sum(asset_projection.evidence_states.values()),
                        state=asset_projection.safe_summary(),
                        source_contract_version=asset_projection.contract_version,
                        company_id=asset_projection.company_id,
                        branch_ids=(asset_projection.branch_id,),
                        authorization_version=asset_projection.authorization_version,
                        limitations=asset_projection.limitations,
                    )
            else:
                workforce_projection = await workforce_lia_context_service.project(
                    session, context=context, employee_id=entity_id
                )
                if workforce_projection is not None:
                    contextual_reference = EvidenceReference(
                        domain=domain,
                        label="Minimum-necessary Workforce readiness context",
                        authority=workforce_projection.contract_version,
                        observed_at=workforce_projection.observed_at,
                        freshness="CURRENT_QUERY",
                        entity_id=workforce_projection.entity_id,
                        evidence_digest=workforce_projection.evidence_digest,
                        count=len(workforce_projection.capability_codes),
                        state=workforce_projection.safe_summary(),
                        source_contract_version=workforce_projection.contract_version,
                        company_id=workforce_projection.company_id,
                        branch_ids=workforce_projection.branch_ids,
                        authorization_version=workforce_projection.authorization_version,
                        limitations=workforce_projection.limitations,
                    )
        if (
            entity_id is not None
            and entity_domain == "scheduling"
            and domains is not None
            and "dispatch" in domains
            and context.has_permission(DispatchPermission.READ)
        ):
            contextual_dispatch_attempted = True
            appointment_branches = (
                frozenset({context.active_branch.id})
                if context.active_branch is not None
                else context.authorized_branch_ids
            )
            authorized_appointment = await session.scalar(
                select(Appointment.id).where(
                    Appointment.id == entity_id,
                    Appointment.company_id == context.company.id,
                    Appointment.branch_id.in_(appointment_branches),
                )
            )
            if authorized_appointment is not None:
                try:
                    assignment = await dispatch_service.detail(
                        session, context=context, appointment_id=entity_id
                    )
                except DispatchNotFound:
                    assignment = None
                state = (
                    f"ASSIGNED|Appointment {assignment.appointment_number} is assigned to "
                    f"{assignment.primary_employee_name or 'no primary technician'}; "
                    f"assignment {assignment.status}; field state {assignment.arrival_state}."
                    if assignment is not None
                    else "UNASSIGNED|This Appointment has no authoritative Dispatch assignment."
                )
                dispatch_payload = {
                    "contract": "DISPATCH.LIA_CONTEXT.v1",
                    "company_id": str(context.company.id),
                    "appointment_id": str(entity_id),
                    "assignment_id": str(assignment.id)
                    if assignment is not None
                    else None,
                    "assignment_version": assignment.version
                    if assignment is not None
                    else None,
                    "primary_employee_id": str(assignment.primary_employee_id)
                    if assignment is not None
                    and assignment.primary_employee_id is not None
                    else None,
                    "status": assignment.status
                    if assignment is not None
                    else "unassigned",
                    "arrival_state": assignment.arrival_state
                    if assignment is not None
                    else None,
                }
                dispatch_reference = EvidenceReference(
                    domain="dispatch",
                    label="Appointment Dispatch context",
                    authority="DISPATCH.LIA_CONTEXT.v1",
                    observed_at=observed_at,
                    freshness="CURRENT_QUERY",
                    entity_id=entity_id,
                    evidence_digest=hashlib.sha256(
                        json.dumps(
                            dispatch_payload, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                    count=1 if assignment is not None else 0,
                    state=state,
                    source_contract_version="DISPATCH.LIA_CONTEXT.v1",
                    company_id=context.company.id,
                    branch_ids=(
                        (assignment.branch_id,)
                        if assignment is not None
                        else (context.active_branch.id,)
                        if context.active_branch is not None
                        else ()
                    ),
                    authorization_version=context.authorization_version,
                    limitations=("read_only_no_assignment_mutation",),
                )
        # Permission checks select adapters before any protected query is executed.
        permitted = tuple(
            adapter
            for adapter in ADAPTERS
            if context.has_permission(adapter.permission)
            and (domains is None or adapter.domain in domains)
            and not (entity_id is not None and adapter.domain in contextual_domains)
            and not (contextual_dispatch_attempted and adapter.domain == "dispatch")
            and (temporal is None or adapter.temporal_kind is not None)
        )
        evidence: list[EvidenceReference] = (
            [contextual_reference] if contextual_reference is not None else []
        )
        if dispatch_reference is not None:
            evidence.append(dispatch_reference)
        for adapter in permitted:
            predicates = [adapter.model.company_id == context.company.id]
            evidence_branch_ids: tuple[Any, ...] = ()
            if hasattr(adapter.model, "branch_id"):
                branch_ids = (
                    frozenset({context.active_branch.id})
                    if context.active_branch is not None
                    else context.authorized_branch_ids
                )
                branch_predicate = adapter.model.branch_id.in_(branch_ids)
                if adapter.model.branch_id.property.columns[0].nullable:
                    branch_predicate = or_(
                        branch_predicate, adapter.model.branch_id.is_(None)
                    )
                predicates.append(branch_predicate)
                evidence_branch_ids = tuple(sorted(branch_ids, key=str))
            if entity_id is not None:
                scoped_entity_column = (
                    adapter.entity_columns.get(entity_domain)
                    if adapter.entity_columns is not None and entity_domain is not None
                    else None
                )
                predicates.append(
                    (
                        scoped_entity_column
                        if scoped_entity_column is not None
                        else adapter.entity_column
                        if adapter.entity_column is not None
                        else adapter.model.id
                    )
                    == entity_id
                )
            if temporal is not None:
                predicates.extend(_temporal_predicates(adapter, temporal))
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
                "period": _temporal_canonical(temporal),
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
                    source_contract_version=f"{adapter.domain.upper()}.BOUNDED_CONTEXT.v1",
                    company_id=context.company.id,
                    branch_ids=evidence_branch_ids,
                    authorization_version=context.authorization_version,
                    period_start=temporal.start_date if temporal else None,
                    period_end=temporal.end_date if temporal else None,
                    period_label=temporal.period_label if temporal else None,
                    timezone=temporal.timezone if temporal else None,
                )
            )
        if temporal is not None:
            supported = {adapter.domain for adapter in permitted}
            for adapter in ADAPTERS:
                if (
                    adapter.domain in (domains or set())
                    and context.has_permission(adapter.permission)
                    and adapter.domain not in supported
                ):
                    evidence.append(
                        _period_unavailable(
                            adapter.domain, adapter.label, temporal, observed_at
                        )
                    )
        if (
            temporal is not None
            and (domains is None or "accounting" in domains)
            and context.has_permission(AccountingPermission.REPORT_READ)
        ):
            evidence.append(
                await self._financial_report(
                    session,
                    context,
                    observed_at,
                    temporal,
                    requested_accounting_basis,
                )
            )
        if (
            context.has_permission(LaunchPlatformPermission.AUDIT_READ)
            and temporal is None
        ):
            for domain, label in (
                ("data-quality", "Data-quality readiness rules"),
                ("launch-readiness", "Real-world launch readiness evidence"),
            ):
                if domains is not None and domain not in domains:
                    continue
                rules = tuple(QUALITY_CATALOG)
                readiness_states: dict[str, int] = {}
                for rule in rules:
                    key = rule.state if domain == "data-quality" else rule.launch_impact
                    readiness_states[key] = readiness_states.get(key, 0) + 1
                evidence.append(
                    _reference(
                        domain=domain,
                        label=label,
                        authority="ACP_READINESS_POLICY_AND_EVIDENCE",
                        observed_at=observed_at,
                        rows=tuple((rule.rule_id, rule.digest) for rule in rules),
                        states=readiness_states,
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
            if temporal is not None:
                query = query.where(
                    LuminaryBriefingRecord.period_start == temporal.start_date,
                    LuminaryBriefingRecord.period_end == temporal.end_date,
                )
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
                        period_start=briefing.period_start,
                        period_end=briefing.period_end,
                        period_label=temporal.period_label if temporal else None,
                        timezone=temporal.timezone if temporal else None,
                    )
                )
            elif temporal is not None:
                evidence.append(
                    _period_unavailable(
                        "luminary", "Luminary owner briefing", temporal, observed_at
                    )
                )
        if context.has_permission(EconomicsPolicyPermission.MEASUREMENT_READ) and (
            domains is None or "business-economics" in domains
        ):
            evidence.extend(
                await self._economics(session, context, observed_at, temporal)
            )
        if context.has_permission(AnalyticsPermission.READ) and (
            domains is None or "beacon" in domains
        ):
            if temporal is None:
                evidence.extend(await self._beacon(session, context, observed_at))
            else:
                evidence.extend(
                    await self._beacon_history(
                        session, context, observed_at, temporal
                    )
                )
        if context.has_permission(AdministrationPermission.COMPANY_ADMINISTER) and (
            domains is None or "migration" in domains
        ):
            evidence.extend(
                await self._migration(session, context, observed_at, temporal)
            )
        if (
            context.has_permission(PayrollPermission.REPORTING_READ)
            or context.has_permission(PayrollPermission.STATEMENT_OWN_READ)
        ) and (domains is None or "payroll" in domains):
            if temporal is None:
                evidence.extend(
                    await self._payroll(
                        session, context, observed_at, entity_id=entity_id
                    )
                )
            else:
                evidence.extend(
                    await self._payroll_period(
                        session, context, observed_at, temporal, entity_id
                    )
                )
        if (
            context.has_permission(WorkforcePermission.READ)
            and (domains is None or "workforce" in domains)
            and not (entity_id is not None and "workforce" in contextual_domains)
            and temporal is None
        ):
            directory = await workforce_operations_service.directory(
                session, context=context
            )
            states: dict[str, int] = {}
            for item in directory.items[:25]:
                states[item.readiness_state] = states.get(item.readiness_state, 0) + 1
            evidence.append(
                _reference(
                    domain="workforce",
                    label="Workforce operational readiness",
                    authority="WORKFORCE.READINESS.v1",
                    observed_at=max(
                        (item.updated_at for item in directory.items[:25]),
                        default=observed_at,
                    ),
                    rows=tuple(
                        (str(item.employee_id), item.readiness_state)
                        for item in directory.items[:25]
                    ),
                    states=states,
                )
            )
        if (
            context.has_permission(CommunicationsPermission.READ)
            and temporal is None
            and (domains is None or "communications" in domains)
        ):
            branch_ids = (
                frozenset({context.active_branch.id})
                if context.active_branch is not None
                else context.authorized_branch_ids
            )
            communication_rows: tuple[NotificationOutbox, ...] = tuple(
                (
                    await session.scalars(
                        select(NotificationOutbox)
                        .where(
                            NotificationOutbox.company_id == context.company.id,
                            NotificationOutbox.branch_id.in_(branch_ids),
                            NotificationOutbox.notification_type.like(
                                "communications.%"
                            ),
                        )
                        .order_by(
                            NotificationOutbox.created_at.desc(),
                            NotificationOutbox.id.desc(),
                        )
                        .limit(25)
                    )
                ).all()
            )
            communication_states: dict[str, int] = {}
            for row in communication_rows:
                communication_states[row.status] = (
                    communication_states.get(row.status, 0) + 1
                )
            evidence.append(
                _reference(
                    domain="communications",
                    label="Customer communication delivery evidence",
                    authority="COMMUNICATIONS.DELIVERY.v1",
                    observed_at=max(
                        (row.updated_at for row in communication_rows),
                        default=observed_at,
                    ),
                    rows=tuple(
                        (str(row.id), row.intent_digest or "unsealed_intent")
                        for row in communication_rows
                    ),
                    states=communication_states,
                )
            )
        return tuple(evidence)

    @staticmethod
    async def _economics(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        temporal: LiaTemporalContext | None,
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
        if temporal is not None:
            query = query.where(
                EconomicsProfitabilityResultRecord.period_start == temporal.start_date,
                EconomicsProfitabilityResultRecord.period_end == temporal.end_date,
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
                temporal=temporal,
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
    async def _beacon_history(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        temporal: LiaTemporalContext,
    ) -> tuple[EvidenceReference, ...]:
        if (temporal.end_date - temporal.start_date).days >= 31:
            return (
                _period_unavailable(
                    "beacon",
                    "Beacon evaluation history",
                    temporal,
                    observed_at,
                    limitation="beacon_history_window_exceeds_31_days",
                ),
            )
        start_at, end_at = _datetime_bounds(temporal)
        history_since = start_at - timedelta(microseconds=1)
        history_until = end_at - timedelta(microseconds=1)
        branch_id = context.active_branch.id if context.active_branch else None
        records = await beacon_evaluation_history_service.deltas(
            session,
            company_id=context.company.id,
            branch_id=branch_id,
            since=history_since,
            until=history_until,
        )
        completed = await beacon_evaluation_history_service.has_completed_run(
            session,
            company_id=context.company.id,
            branch_id=branch_id,
            since=history_since,
            until=history_until,
        )
        if not completed:
            return (
                _period_unavailable(
                    "beacon",
                    "Beacon evaluation history",
                    temporal,
                    observed_at,
                    limitation="no_completed_beacon_evaluation_in_period",
                ),
            )

        states = {
            disposition.value: sum(
                item.disposition is disposition for item in records
            )
            for disposition in EvaluationDisposition
        }
        canonical = {
            "company_id": str(context.company.id),
            "branch_id": str(branch_id) if branch_id else None,
            "period": _temporal_canonical(temporal),
            "records": sorted(
                (
                    str(item.id),
                    str(item.run_id),
                    str(item.condition_key),
                    item.evidence_digest,
                    item.disposition.value,
                    item.evaluated_at.isoformat(),
                    item.evidence_as_of.isoformat(),
                )
                for item in records
            ),
            "states": states,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        state = ", ".join(
            f"{key}={value}" for key, value in sorted(states.items()) if value
        )
        return (
            EvidenceReference(
                domain="beacon",
                label="Beacon evaluation history",
                authority="AUTHORITATIVE_SIGNAL_HISTORY",
                observed_at=max(
                    (item.evaluated_at for item in records), default=observed_at
                ),
                freshness="PERSISTED_EVIDENCE",
                evidence_digest=digest,
                count=len(records),
                state=state or "no Beacon changes recorded",
                source_contract_version="BEACON.EVALUATION_HISTORY.v1",
                company_id=context.company.id,
                branch_ids=(branch_id,) if branch_id else (),
                authorization_version=context.authorization_version,
                limitations=(
                    "Historical dispositions explain recorded Beacon evaluations; they do not replace current lifecycle state or authorize remediation.",
                ),
                period_start=temporal.start_date,
                period_end=temporal.end_date,
                period_label=temporal.period_label,
                timezone=temporal.timezone,
            ),
        )

    @staticmethod
    async def _migration(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        temporal: LiaTemporalContext | None,
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
        if temporal is not None:
            start_at, end_at = _datetime_bounds(temporal)
            query = query.where(
                HcpMigrationMasterRun.started_at < end_at,
                func.coalesce(
                    HcpMigrationMasterRun.completed_at, HcpMigrationMasterRun.started_at
                )
                >= start_at,
            )
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
                temporal=temporal,
            ),
        )

    @staticmethod
    async def _payroll(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        *,
        entity_id: Any | None = None,
    ) -> tuple[EvidenceReference, ...]:
        if context.has_permission(PayrollPermission.REPORTING_READ):
            if entity_id is not None and context.has_permission(
                TimekeepingPermission.ADMIN_READ
            ):
                period = await session.scalar(
                    select(PayPeriod)
                    .where(PayPeriod.company_id == context.company.id)
                    .order_by(PayPeriod.period_end.desc(), PayPeriod.id.desc())
                    .limit(1)
                )
                if period is not None:
                    operations = await PayrollOperationsService().period(
                        session, context=context, pay_period_id=period.id
                    )
                    employee = next(
                        (
                            item
                            for item in operations.employees
                            if item.employee_id == entity_id
                        ),
                        None,
                    )
                    if employee is not None:
                        states = {
                            "payroll_review_status:"
                            + employee.payroll_review_status: 1,
                            "compensation:" + employee.compensation_readiness: 1,
                            "withholding:" + employee.withholding_readiness: 1,
                            "gross_pay:" + employee.gross_pay_readiness: 1,
                            **{
                                "blocker:" + code: 1
                                for code in employee.exception_codes
                            },
                        }
                        canonical = {
                            "contract": operations.contract_version,
                            "employee_id": str(employee.employee_id),
                            "pay_period_id": str(period.id),
                            "states": states,
                            "time_snapshot_state": employee.time_snapshot_state,
                        }
                        digest = hashlib.sha256(
                            json.dumps(
                                canonical,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest()
                        return (
                            EvidenceReference(
                                domain="payroll",
                                label=f"Payroll readiness for {employee.display_name}",
                                authority=operations.contract_version,
                                observed_at=observed_at,
                                freshness="CURRENT_QUERY",
                                entity_id=employee.employee_id,
                                evidence_digest=digest,
                                count=len(employee.exception_codes),
                                state=", ".join(sorted(states)),
                                source_contract_version=operations.contract_version,
                                company_id=context.company.id,
                                branch_ids=(employee.home_branch_id,)
                                if employee.home_branch_id is not None
                                else (),
                                authorization_version=context.authorization_version,
                                limitations=(
                                    "protected_payroll_values_excluded",
                                    "owner_and_accountant_input_ownership_requires_explicit_source_evidence",
                                ),
                            ),
                        )
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

    @staticmethod
    async def _payroll_period(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        temporal: LiaTemporalContext,
        entity_id: Any | None,
    ) -> tuple[EvidenceReference, ...]:
        if not context.has_permission(PayrollPermission.REPORTING_READ):
            return (
                _period_unavailable(
                    "payroll",
                    "Historical Payroll period evidence",
                    temporal,
                    observed_at,
                ),
            )
        period = await session.scalar(
            select(PayPeriod).where(
                PayPeriod.company_id == context.company.id,
                PayPeriod.period_start == temporal.start_date,
                PayPeriod.period_end == temporal.end_date,
            )
        )
        if period is None:
            return (
                _period_unavailable(
                    "payroll",
                    "Historical Payroll period evidence",
                    temporal,
                    observed_at,
                ),
            )
        operations = await PayrollOperationsService().period(
            session, context=context, pay_period_id=period.id
        )
        employees = tuple(
            item
            for item in operations.employees
            if entity_id is None or item.employee_id == entity_id
        )
        states: dict[str, int] = {}
        for employee in employees:
            key = f"review:{employee.payroll_review_status}"
            states[key] = states.get(key, 0) + 1
            for code in employee.exception_codes:
                blocker = f"blocker:{code}"
                states[blocker] = states.get(blocker, 0) + 1
        return (
            _reference(
                domain="payroll",
                label="Payroll period readiness metadata",
                authority=operations.contract_version,
                observed_at=observed_at,
                rows=tuple(
                    (str(item.employee_id), item.payroll_review_status)
                    for item in employees
                ),
                states=states,
                temporal=temporal,
                limitations=("protected_payroll_values_excluded",),
            ),
        )

    @staticmethod
    async def _financial_report(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
        temporal: LiaTemporalContext,
        requested_basis: str | None,
    ) -> EvidenceReference:
        try:
            result = await financial_reporting_service.income_statement(
                session,
                context=context,
                start_date=temporal.start_date,
                end_date=temporal.end_date,
                branch_id=context.active_branch.id if context.active_branch else None,
            )
        except (ReportingIntegrityError, ReportingNotFound, ReportingRequestError):
            return _period_unavailable(
                "accounting", "Native income statement", temporal, observed_at
            )
        basis = result.manifest.accounting_basis
        if requested_basis is not None and requested_basis != basis:
            return _period_unavailable(
                "accounting",
                f"Requested {requested_basis} income statement",
                temporal,
                observed_at,
                limitation=f"available_native_basis:{basis}",
                accounting_basis=basis,
            )
        return EvidenceReference(
            domain="accounting",
            label="Native income statement",
            authority="ACP_POSTED_LEDGER_AUTHORITY",
            observed_at=result.manifest.generated_at,
            freshness=result.quality.freshness,
            evidence_digest=result.manifest.checksum,
            count=len(result.revenue) + len(result.expenses),
            state=(
                f"{result.manifest.currency} total revenue={result.total_revenue}; "
                f"total expenses={result.total_expenses}; net income={result.net_income}; "
                f"basis={basis}; integrity={result.quality.integrity}"
            ),
            source_contract_version=result.manifest.definition_version,
            company_id=context.company.id,
            branch_ids=(context.active_branch.id,) if context.active_branch else (),
            authorization_version=context.authorization_version,
            period_start=temporal.start_date,
            period_end=temporal.end_date,
            period_label=temporal.period_label,
            timezone=temporal.timezone,
            accounting_basis=basis,
        )


def _reference(
    *,
    domain: str,
    label: str,
    authority: str,
    observed_at: datetime,
    rows: tuple[tuple[str, str], ...],
    states: dict[str, int],
    temporal: LiaTemporalContext | None = None,
    limitations: tuple[str, ...] = (),
    accounting_basis: str | None = None,
) -> EvidenceReference:
    canonical = {
        "domain": domain,
        "rows": sorted(rows),
        "states": states,
        "period": _temporal_canonical(temporal),
        "accounting_basis": accounting_basis,
    }
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
        limitations=limitations,
        period_start=temporal.start_date if temporal else None,
        period_end=temporal.end_date if temporal else None,
        period_label=temporal.period_label if temporal else None,
        timezone=temporal.timezone if temporal else None,
        accounting_basis=accounting_basis,
    )


def _temporal_predicates(
    adapter: AdapterSpec, temporal: LiaTemporalContext
) -> tuple[Any, ...]:
    start_column = adapter.temporal_start_column
    end_column = adapter.temporal_end_column
    if start_column is None:
        return ()
    if adapter.temporal_kind == "date_start":
        return (
            start_column >= temporal.start_date,
            start_column <= temporal.end_date,
        )
    if adapter.temporal_kind == "date_overlap":
        if end_column is None:
            return ()
        return (
            start_column <= temporal.end_date,
            end_column >= temporal.start_date,
        )
    start_at, end_at = _datetime_bounds(temporal)
    if adapter.temporal_kind == "datetime_start":
        return (
            start_column >= start_at,
            start_column < end_at,
        )
    if adapter.temporal_kind == "datetime_overlap":
        if end_column is None:
            return ()
        return (
            start_column < end_at,
            end_column >= start_at,
        )
    return ()


def _datetime_bounds(temporal: LiaTemporalContext) -> tuple[datetime, datetime]:
    zone = ZoneInfo(temporal.timezone)
    start_at = datetime.combine(temporal.start_date, time.min, zone).astimezone(UTC)
    end_at = datetime.combine(
        temporal.end_date + timedelta(days=1), time.min, zone
    ).astimezone(UTC)
    return start_at, end_at


def _temporal_canonical(temporal: LiaTemporalContext | None) -> dict[str, str] | None:
    if temporal is None:
        return None
    return {
        "start_date": temporal.start_date.isoformat(),
        "end_date": temporal.end_date.isoformat(),
        "period_label": temporal.period_label,
        "timezone": temporal.timezone,
    }


def _period_unavailable(
    domain: str,
    label: str,
    temporal: LiaTemporalContext,
    observed_at: datetime,
    *,
    limitation: str = "authoritative_historical_filter_unavailable",
    accounting_basis: str | None = None,
) -> EvidenceReference:
    return _reference(
        domain=domain,
        label=label,
        authority="PERIOD_AUTHORITY_UNAVAILABLE",
        observed_at=observed_at,
        rows=(),
        states={"period_unavailable": 1},
        temporal=temporal,
        limitations=(limitation,),
        accounting_basis=accounting_basis,
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
    if context.has_permission(WorkforcePermission.READ):
        domains.add("workforce")
    if context.has_permission(CommunicationsPermission.READ):
        domains.add("communications")
    if context.has_permission(
        PayrollPermission.REPORTING_READ
    ) or context.has_permission(PayrollPermission.STATEMENT_OWN_READ):
        domains.add("payroll")
    if context.has_permission(LuminaryPermission.READ):
        domains.add("luminary")
    if context.has_permission(LaunchPlatformPermission.AUDIT_READ):
        domains.update({"audit", "data-quality", "launch-readiness"})
    if context.has_permission(AccountingPermission.REPORT_READ):
        domains.add("accounting")
    if context.has_permission(TimekeepingPermission.ADMIN_READ):
        domains.add("timekeeping")
    if context.has_permission(DispatchPermission.READ):
        domains.add("dispatch")
    if context.has_permission(PriceBookPermission.READ):
        domains.add("price-book")
    return domains
