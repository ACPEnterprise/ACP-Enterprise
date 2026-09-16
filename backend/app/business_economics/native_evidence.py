"""Read-only admission of authoritative ACP-native operational evidence.

This projection does not manufacture profitability results.  It makes already
accepted owning-domain facts visible to Economics while preserving the exact
boundary between invoiced revenue, worked time, material quantity/cost, and
reconciled Accounting evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer
from app.inventory.models import InventoryReservation, MaterialIssue, StockMovement
from app.invoicing.models import ARLedgerEntry, Invoice, PaymentReceiptEvidence
from app.jobs.models import Job
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import JobWorkedIntervalRevision

CONTRACT_VERSION: Final = "economics.native-evidence-admission.v1"
MAX_SOURCE_ROWS: Final = 5000
_INVOICE_EVIDENCE_STATES: Final = (
    "issued",
    "partially_paid",
    "adjusted",
    "paid",
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _minor(value: Decimal) -> int:
    return int(value * 100)


class NativeEconomicsEvidenceService:
    """Project accepted source facts without persistence or policy interpretation."""

    async def project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
        company_id = context.company.id
        branch_id = context.active_branch.id if context.active_branch else None
        authorized_branch_ids = context.authorized_branch_ids

        jobs_query = (
            select(Job, Customer, Branch)
            .join(Customer, Customer.id == Job.customer_id)
            .join(Branch, Branch.id == Job.branch_id)
            .where(
                Job.company_id == company_id,
                Job.branch_id.in_(authorized_branch_ids),
            )
            .order_by(Job.updated_at.desc(), Job.id.desc())
            .limit(MAX_SOURCE_ROWS)
        )
        invoices_query = (
            select(Invoice)
            .where(
                Invoice.company_id == company_id,
                Invoice.branch_id.in_(authorized_branch_ids),
                Invoice.issue_date >= period_start,
                Invoice.issue_date <= period_end,
                Invoice.status.in_(_INVOICE_EVIDENCE_STATES),
            )
            .order_by(Invoice.issue_date.desc(), Invoice.id.desc())
            .limit(MAX_SOURCE_ROWS)
        )
        intervals_query = (
            select(JobWorkedIntervalRevision)
            .where(
                JobWorkedIntervalRevision.company_id == company_id,
                JobWorkedIntervalRevision.branch_id.in_(authorized_branch_ids),
                JobWorkedIntervalRevision.start_at <= end_at,
                JobWorkedIntervalRevision.stop_at >= start_at,
                JobWorkedIntervalRevision.validity == "valid",
                JobWorkedIntervalRevision.confidence == "authoritative",
                JobWorkedIntervalRevision.correction_state != "superseded",
                ~exists().where(
                    JobWorkedIntervalRevision.supersedes_revision_id
                    == JobWorkedIntervalRevision.id
                ),
            )
            .order_by(JobWorkedIntervalRevision.start_at.desc())
            .limit(MAX_SOURCE_ROWS)
        )
        materials_query = (
            select(MaterialIssue, InventoryReservation, StockMovement)
            .join(
                InventoryReservation,
                (InventoryReservation.company_id == MaterialIssue.company_id)
                & (InventoryReservation.id == MaterialIssue.reservation_id),
            )
            .join(
                StockMovement,
                (StockMovement.company_id == MaterialIssue.company_id)
                & (StockMovement.id == MaterialIssue.movement_id),
            )
            .where(
                MaterialIssue.company_id == company_id,
                MaterialIssue.branch_id.in_(authorized_branch_ids),
                MaterialIssue.occurred_at >= start_at,
                MaterialIssue.occurred_at <= end_at,
                InventoryReservation.demand_type == "job",
            )
            .order_by(MaterialIssue.occurred_at.desc(), MaterialIssue.id.desc())
            .limit(MAX_SOURCE_ROWS)
        )
        settlements_query = (
            select(ARLedgerEntry, Invoice, PaymentReceiptEvidence)
            .join(
                Invoice,
                (Invoice.company_id == ARLedgerEntry.company_id)
                & (Invoice.id == ARLedgerEntry.invoice_id),
            )
            .join(
                PaymentReceiptEvidence,
                (PaymentReceiptEvidence.company_id == ARLedgerEntry.company_id)
                & (PaymentReceiptEvidence.receipt_id == ARLedgerEntry.source_id),
            )
            .where(
                ARLedgerEntry.company_id == company_id,
                ARLedgerEntry.branch_id.in_(authorized_branch_ids),
                ARLedgerEntry.entry_type.in_(
                    ("payment_application", "application_reversal")
                ),
                ARLedgerEntry.occurred_at >= start_at,
                ARLedgerEntry.occurred_at <= end_at,
            )
            .order_by(ARLedgerEntry.occurred_at.desc(), ARLedgerEntry.id.desc())
            .limit(MAX_SOURCE_ROWS)
        )
        if branch_id is not None:
            jobs_query = jobs_query.where(Job.branch_id == branch_id)
            invoices_query = invoices_query.where(Invoice.branch_id == branch_id)
            intervals_query = intervals_query.where(
                JobWorkedIntervalRevision.branch_id == branch_id
            )
            materials_query = materials_query.where(
                MaterialIssue.branch_id == branch_id
            )
            settlements_query = settlements_query.where(
                ARLedgerEntry.branch_id == branch_id
            )

        invoices = tuple((await session.scalars(invoices_query)).all())
        intervals = tuple((await session.scalars(intervals_query)).all())
        material_rows = tuple((await session.execute(materials_query)).all())
        settlement_rows = tuple((await session.execute(settlements_query)).all())
        referenced_job_ids = {
            *(item.job_id for item in invoices),
            *(item.job_id for item in intervals),
            *(reservation.demand_id for _, reservation, _ in material_rows),
            *(invoice.job_id for _, invoice, _ in settlement_rows),
        }
        period_identity = or_(
            Job.created_at.between(start_at, end_at),
            Job.started_at.between(start_at, end_at),
            Job.completed_at.between(start_at, end_at),
        )
        jobs_query = jobs_query.where(
            or_(period_identity, Job.id.in_(referenced_job_ids))
            if referenced_job_ids
            else period_identity
        )
        job_rows = tuple((await session.execute(jobs_query)).all())

        jobs: dict[UUID, dict[str, Any]] = {}
        for job, customer, branch in job_rows:
            jobs[job.id] = {
                "job_id": str(job.id),
                "job_number": job.job_number,
                "job_status": job.status,
                "customer_id": str(customer.id),
                "customer_name": customer.display_name,
                "branch_id": str(branch.id),
                "branch_name": branch.name,
                "service_category": job.job_type_code,
                "references": [
                    self._reference(
                        family="JOB_IDENTITY",
                        record_type="job",
                        record_id=job.id,
                        source_version=job.concurrency_version,
                        as_of=job.updated_at,
                        payload={
                            "company_id": job.company_id,
                            "branch_id": job.branch_id,
                            "customer_id": job.customer_id,
                            "status": job.status,
                            "job_type_code": job.job_type_code,
                        },
                    )
                ],
                "invoiced_revenue_minor": None,
                "currency": None,
                "accepted_worked_seconds": None,
                "material_cost_minor": None,
                "material_quantity_evidence_count": 0,
                "settlement_applied_minor": None,
            }

        invoice_totals: dict[UUID, int] = defaultdict(int)
        invoice_currency: dict[UUID, set[str]] = defaultdict(set)
        for invoice in invoices:
            row = jobs.get(invoice.job_id)
            if row is None:
                continue
            invoice_totals[invoice.job_id] += _minor(invoice.total_amount)
            invoice_currency[invoice.job_id].add(invoice.currency.upper())
            row["references"].append(
                self._reference(
                    family="REVENUE",
                    record_type="invoice",
                    record_id=invoice.id,
                    source_version=invoice.version,
                    as_of=invoice.issued_at or invoice.updated_at,
                    payload={
                        "job_id": invoice.job_id,
                        "status": invoice.status,
                        "basis": "invoiced",
                        "amount": invoice.total_amount,
                        "currency": invoice.currency,
                    },
                )
            )
        for job_id, amount in invoice_totals.items():
            jobs[job_id]["invoiced_revenue_minor"] = amount
            currencies = invoice_currency[job_id]
            jobs[job_id]["currency"] = (
                next(iter(currencies)) if len(currencies) == 1 else None
            )

        labor_totals: dict[UUID, int] = defaultdict(int)
        for interval in intervals:
            row = jobs.get(interval.job_id)
            if row is None:
                continue
            labor_totals[interval.job_id] += interval.duration_seconds
            row["references"].append(
                self._reference(
                    family="DIRECT_LABOR",
                    record_type="accepted_job_work_interval",
                    record_id=interval.id,
                    source_version=interval.revision_number,
                    as_of=interval.created_at,
                    payload={
                        "interval_id": interval.interval_id,
                        "employee_id": interval.employee_id,
                        "job_id": interval.job_id,
                        "duration_seconds": interval.duration_seconds,
                        "validity": interval.validity,
                        "confidence": interval.confidence,
                    },
                )
            )
        for job_id, seconds in labor_totals.items():
            jobs[job_id]["accepted_worked_seconds"] = seconds
            attributed = tuple(item for item in intervals if item.job_id == job_id)
            jobs[job_id]["references"].append(
                self._reference(
                    family="WORKFORCE_ATTRIBUTION",
                    record_type="employee_job_work_attribution",
                    record_id=attributed[0].id,
                    source_version=max(item.revision_number for item in attributed),
                    as_of=max(item.created_at for item in attributed),
                    payload={
                        "job_id": job_id,
                        "employee_ids": sorted(
                            {str(item.employee_id) for item in attributed}
                        ),
                        "accepted_worked_seconds": seconds,
                    },
                )
            )

        material_totals: dict[UUID, int] = defaultdict(int)
        material_cost_complete: dict[UUID, bool] = defaultdict(lambda: True)
        material_currencies: set[str] = set()
        for issue, reservation, movement in material_rows:
            row = jobs.get(reservation.demand_id)
            if row is None:
                continue
            row["material_quantity_evidence_count"] += 1
            if movement.unit_cost is None or movement.currency is None:
                material_cost_complete[reservation.demand_id] = False
            else:
                material_currencies.add(movement.currency.upper())
                direction = -1 if issue.issue_type == "reversal" else 1
                material_totals[reservation.demand_id] += direction * _minor(
                    issue.quantity * movement.unit_cost
                )
            row["references"].append(
                self._reference(
                    family="DIRECT_MATERIAL",
                    record_type="material_issue",
                    record_id=issue.id,
                    source_version=1,
                    as_of=issue.posted_at,
                    payload={
                        "job_id": reservation.demand_id,
                        "item_id": issue.item_id,
                        "quantity": issue.quantity,
                        "unit": issue.stocking_unit,
                        "unit_cost": movement.unit_cost,
                        "currency": movement.currency,
                        "valuation_method": movement.valuation_method,
                    },
                )
            )
        for job_id, row in jobs.items():
            if (
                row["material_quantity_evidence_count"]
                and material_cost_complete[job_id]
            ):
                row["material_cost_minor"] = material_totals[job_id]

        settlement_totals: dict[UUID, int] = defaultdict(int)
        for entry, invoice, receipt in settlement_rows:
            row = jobs.get(invoice.job_id)
            if row is None:
                continue
            settlement_totals[invoice.job_id] += _minor(entry.amount)
            row["references"].append(
                self._reference(
                    family="SETTLEMENT",
                    record_type="verified_payment_application",
                    record_id=entry.id,
                    source_version=entry.source_version,
                    as_of=entry.occurred_at,
                    payload={
                        "receipt_id": receipt.receipt_id,
                        "invoice_id": invoice.id,
                        "job_id": invoice.job_id,
                        "entry_type": entry.entry_type,
                        "amount": entry.amount,
                        "currency": entry.currency,
                        "receipt_evidence_digest": receipt.evidence_digest,
                    },
                )
            )
        for job_id, amount in settlement_totals.items():
            jobs[job_id]["settlement_applied_minor"] = amount

        references = [ref for row in jobs.values() for ref in row["references"]]
        accounting_conflicts = sum(
            invoice.accounting_status == "reconciliation_required"
            for invoice in invoices
        )
        posted = sum(invoice.accounting_status == "posted" for invoice in invoices)
        families = {
            "REVENUE": self._family(
                "AVAILABLE" if invoices else "ABSENT",
                len(invoices),
                "ACP issued Invoice; invoiced basis is not earned revenue or settlement.",
            ),
            "JOB_IDENTITY": self._family(
                "AVAILABLE" if jobs else "ABSENT",
                len(jobs),
                "ACP Job lifecycle identity.",
            ),
            "CUSTOMER_ATTRIBUTION": self._family(
                "AVAILABLE" if jobs else "ABSENT",
                len(jobs),
                "Job foreign-key attribution to ACP Customer.",
            ),
            "BRANCH_ATTRIBUTION": self._family(
                "AVAILABLE" if jobs else "ABSENT",
                len(jobs),
                "Job foreign-key attribution to authorized ACP Branch.",
            ),
            "SERVICE_CATEGORY": self._family(
                "AVAILABLE"
                if jobs and all(row["service_category"] for row in jobs.values())
                else "PARTIAL"
                if jobs
                else "ABSENT",
                sum(bool(row["service_category"]) for row in jobs.values()),
                "Explicit canonical Job type code only; free text is not classified.",
            ),
            "DIRECT_LABOR": self._family(
                "AVAILABLE" if intervals else "ABSENT",
                len(intervals),
                "Accepted authoritative Job-work duration; wage cost is not inferred.",
            ),
            "WORKFORCE_ATTRIBUTION": self._family(
                "AVAILABLE" if intervals else "ABSENT",
                len(intervals),
                "Accepted Employee-to-Job work attribution; no ranking, pay rate, or employment conclusion.",
            ),
            "DIRECT_MATERIAL": self._family(
                "AVAILABLE"
                if material_rows and all(material_cost_complete.values())
                else "PARTIAL"
                if material_rows
                else "ABSENT",
                len(material_rows),
                "Job-demand material issues; cost is available only with an authoritative Inventory valuation layer.",
            ),
            "ACCOUNTING": self._family(
                "CONFLICTING"
                if accounting_conflicts
                else "AVAILABLE"
                if posted
                else "PARTIAL"
                if invoices
                else "ABSENT",
                posted,
                "Only posted Invoice accounting receipts are admitted; pending operational invoices remain non-Accounting evidence.",
            ),
            "SETTLEMENT": self._family(
                "AVAILABLE" if settlement_rows else "ABSENT",
                len(settlement_rows),
                "Verified receipt application to an Invoice; distinct from earned revenue, Accounting recognition, and cash deposit.",
            ),
        }
        ordered_jobs = sorted(
            jobs.values(), key=lambda item: (item["job_number"], item["job_id"])
        )
        currencies = {
            str(row["currency"]) for row in ordered_jobs if row["currency"] is not None
        }
        material_cost_known = [
            row for row in ordered_jobs if row["material_quantity_evidence_count"]
        ]
        payload: dict[str, object] = {
            "contract_version": CONTRACT_VERSION,
            "authority": "accepted_acp_native_owning_domain_facts",
            "period": {
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
            },
            "families": families,
            "admitted_reference_count": len(references),
            "summary": {
                "job_count": len(ordered_jobs),
                "invoiced_revenue_minor": (
                    sum(int(row["invoiced_revenue_minor"] or 0) for row in ordered_jobs)
                    if invoices and len(currencies) == 1
                    else None
                ),
                "currency": next(iter(currencies)) if len(currencies) == 1 else None,
                "accepted_worked_seconds": (
                    sum(
                        int(row["accepted_worked_seconds"] or 0) for row in ordered_jobs
                    )
                    if intervals
                    else None
                ),
                "material_cost_minor": (
                    sum(
                        int(row["material_cost_minor"] or 0)
                        for row in material_cost_known
                    )
                    if material_cost_known
                    and all(
                        row["material_cost_minor"] is not None
                        for row in material_cost_known
                    )
                    and len(material_currencies) == 1
                    else None
                ),
                "material_currency": (
                    next(iter(material_currencies))
                    if len(material_currencies) == 1
                    else None
                ),
                "settlement_applied_minor": (
                    sum(
                        int(row["settlement_applied_minor"] or 0)
                        for row in ordered_jobs
                    )
                    if settlement_rows and len(currencies) == 1
                    else None
                ),
            },
            "jobs": ordered_jobs,
            "limitations": [
                "Invoiced revenue is not substituted for earned revenue, settlement, or cash.",
                "Accepted worked duration is not substituted for paid time or labor cost.",
                "Material quantity without a valuation layer does not become material cost or zero.",
                "Native source admission does not create a profitability result or recommendation.",
            ],
        }
        payload["evidence_digest"] = _digest(payload)
        return payload

    @staticmethod
    def _family(state: str, count: int, limitation: str) -> dict[str, object]:
        return {"state": state, "reference_count": count, "limitation": limitation}

    @staticmethod
    def _reference(
        *,
        family: str,
        record_type: str,
        record_id: UUID,
        source_version: int,
        as_of: datetime,
        payload: object,
    ) -> dict[str, object]:
        return {
            "family": family,
            "source": "ACP_NATIVE",
            "authority": "accepted_owning_domain_record",
            "record_type": record_type,
            "record_id": str(record_id),
            "source_version": source_version,
            "as_of": as_of.isoformat(),
            "digest": _digest(payload),
        }
