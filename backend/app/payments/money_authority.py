from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.estimates.models import EstimateJobConversion, EstimateRevision
from app.invoicing.models import Invoice, ManualPaymentReceipt
from app.jobs.models import Job, JobAppointmentLink
from app.payments.models import (
    PaymentIntent,
    PaymentReceipt,
    PaymentTermPolicy,
    Settlement,
)
from app.platform.branch.models import Branch
from app.scheduling.models import Appointment

EvidenceState = Literal[
    "AVAILABLE", "MEASURED_ZERO", "INCOMPLETE", "CONFLICTING", "UNAVAILABLE"
]


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    amount: Decimal | None
    currency: str | None
    evidence_state: EvidenceState
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class ExpectedCollectionEvidence:
    amount: Decimal | None
    currency: str | None
    evidence_state: EvidenceState
    evidence_basis: str


def compose_expected_collections(
    *,
    cod: ExpectedCollectionEvidence,
    due_today: ExpectedCollectionEvidence,
) -> MoneyAmount:
    incomplete = {"INCOMPLETE", "CONFLICTING", "UNAVAILABLE"}
    if cod.evidence_state in incomplete or due_today.evidence_state in incomplete:
        currency = cod.currency if cod.currency == due_today.currency else None
        return MoneyAmount(
            None,
            currency,
            "INCOMPLETE",
            "Expected collections are incomplete because one or more components lack authoritative evidence.",
        )
    currencies = {
        value.currency
        for value in (cod, due_today)
        if value.amount is not None and value.currency is not None
    }
    if len(currencies) > 1:
        return MoneyAmount(
            None, None, "CONFLICTING", "Expected collections use multiple currencies."
        )
    values = tuple(
        value.amount for value in (cod, due_today) if value.amount is not None
    )
    return MoneyAmount(
        sum(values, Decimal("0.00")),
        next(iter(currencies)) if currencies else None,
        "AVAILABLE" if values else "MEASURED_ZERO",
    )


def _summarize_amounts(
    values: tuple[tuple[Decimal, str], ...], *, unavailable: str | None = None
) -> MoneyAmount:
    if unavailable is not None:
        return MoneyAmount(None, None, "UNAVAILABLE", unavailable)
    currencies = {currency for _, currency in values}
    if len(currencies) > 1:
        return MoneyAmount(
            None,
            None,
            "CONFLICTING",
            "Multiple currencies cannot be combined into one monetary total.",
        )
    if not values:
        return MoneyAmount(Decimal("0.00"), None, "MEASURED_ZERO")
    return MoneyAmount(
        sum((amount for amount, _ in values), Decimal("0.00")),
        next(iter(currencies)),
        "AVAILABLE",
    )


def _utc_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(settings.business_timezone)
    return (
        datetime.combine(start, time.min, tzinfo=zone).astimezone(timezone.utc),
        datetime.combine(end, time.max, tzinfo=zone).astimezone(timezone.utc),
    )


class MoneyAuthorityService:
    @staticmethod
    def _resolve_term(
        policies: tuple[PaymentTermPolicy, ...], customer_id: UUID
    ) -> PaymentTermPolicy | None:
        customer = tuple(row for row in policies if row.customer_id == customer_id)
        candidates = customer or tuple(
            row for row in policies if row.customer_id is None
        )
        return max(
            candidates, key=lambda row: (row.effective_from, row.version), default=None
        )

    async def projection(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        authorized_branch_ids: frozenset[UUID],
        period_start: date,
        period_end: date,
        as_of: date,
        branch_id: UUID | None,
    ) -> dict[str, object]:
        branches = (
            frozenset({branch_id})
            if branch_id is not None and branch_id in authorized_branch_ids
            else authorized_branch_ids
            if branch_id is None
            else frozenset()
        )
        start_at, end_at = _utc_bounds(period_start, period_end)
        company_branch_ids = frozenset(
            (
                await session.scalars(
                    select(Branch.id).where(Branch.company_id == company_id)
                )
            ).all()
        )
        has_company_wide_branch_scope = company_branch_ids.issubset(
            authorized_branch_ids
        )

        receipt_rows = tuple(
            (
                await session.execute(
                    select(PaymentReceipt, PaymentIntent)
                    .join(
                        PaymentIntent,
                        (PaymentIntent.company_id == PaymentReceipt.company_id)
                        & (PaymentIntent.id == PaymentReceipt.intent_id),
                    )
                    .where(
                        PaymentReceipt.company_id == company_id,
                        PaymentReceipt.branch_id.in_(branches),
                        PaymentReceipt.captured_at >= start_at,
                        PaymentReceipt.captured_at <= end_at,
                    )
                    .order_by(PaymentReceipt.captured_at.desc(), PaymentReceipt.id)
                )
            ).all()
        )
        manual_collection_rows = tuple(
            (
                await session.scalars(
                    select(ManualPaymentReceipt)
                    .where(
                        ManualPaymentReceipt.company_id == company_id,
                        ManualPaymentReceipt.branch_id.in_(branches),
                        ManualPaymentReceipt.occurred_at >= start_at,
                        ManualPaymentReceipt.occurred_at <= end_at,
                    )
                    .order_by(
                        ManualPaymentReceipt.occurred_at.desc(),
                        ManualPaymentReceipt.id,
                    )
                )
            ).all()
        )
        invoice_rows = tuple(
            (
                await session.scalars(
                    select(Invoice)
                    .where(
                        Invoice.company_id == company_id,
                        Invoice.branch_id.in_(branches),
                        Invoice.status.in_(
                            ("draft", "issued", "partially_paid", "adjusted")
                        ),
                        Invoice.open_amount > 0,
                        Invoice.due_date == as_of,
                    )
                    .order_by(Invoice.due_date, Invoice.invoice_number, Invoice.id)
                )
            ).all()
        )

        scheduled_rows = tuple(
            (
                await session.execute(
                    select(
                        Job,
                        Appointment,
                        EstimateJobConversion,
                        EstimateRevision,
                    )
                    .join(
                        JobAppointmentLink,
                        (JobAppointmentLink.company_id == Job.company_id)
                        & (JobAppointmentLink.branch_id == Job.branch_id)
                        & (JobAppointmentLink.job_id == Job.id),
                    )
                    .join(
                        Appointment,
                        (Appointment.company_id == JobAppointmentLink.company_id)
                        & (Appointment.branch_id == JobAppointmentLink.branch_id)
                        & (Appointment.id == JobAppointmentLink.appointment_id),
                    )
                    .outerjoin(
                        EstimateJobConversion,
                        (EstimateJobConversion.company_id == Job.company_id)
                        & (EstimateJobConversion.branch_id == Job.branch_id)
                        & (EstimateJobConversion.job_id == Job.id),
                    )
                    .outerjoin(
                        EstimateRevision,
                        (
                            EstimateRevision.company_id
                            == EstimateJobConversion.company_id
                        )
                        & (
                            EstimateRevision.id
                            == EstimateJobConversion.estimate_revision_id
                        ),
                    )
                    .where(
                        Job.company_id == company_id,
                        Job.branch_id.in_(branches),
                        Job.status != "cancelled",
                        Appointment.status.in_(("scheduled", "confirmed", "completed")),
                        Appointment.arrival_window_start_at
                        >= _utc_bounds(as_of, as_of)[0],
                        Appointment.arrival_window_start_at
                        <= _utc_bounds(as_of, as_of)[1],
                        ~exists(
                            select(Invoice.id).where(
                                Invoice.company_id == Job.company_id,
                                Invoice.job_id == Job.id,
                                Invoice.status.not_in(("cancelled", "voided")),
                            )
                        ),
                    )
                    .order_by(Appointment.arrival_window_start_at, Job.id)
                )
            ).all()
        )
        scheduled_by_job: dict[
            UUID,
            tuple[
                Job, Appointment, EstimateJobConversion | None, EstimateRevision | None
            ],
        ] = {}
        for job, appointment, conversion, revision in scheduled_rows:
            scheduled_by_job.setdefault(
                job.id, (job, appointment, conversion, revision)
            )
        customer_ids = {job.customer_id for job, _, _, _ in scheduled_by_job.values()}
        policies: tuple[PaymentTermPolicy, ...] = ()
        if customer_ids:
            policies = tuple(
                (
                    await session.scalars(
                        select(PaymentTermPolicy).where(
                            PaymentTermPolicy.company_id == company_id,
                            PaymentTermPolicy.approved.is_(True),
                            PaymentTermPolicy.effective_from <= as_of,
                            or_(
                                PaymentTermPolicy.effective_through.is_(None),
                                PaymentTermPolicy.effective_through >= as_of,
                            ),
                            or_(
                                PaymentTermPolicy.customer_id.is_(None),
                                PaymentTermPolicy.customer_id.in_(customer_ids),
                            ),
                        )
                    )
                ).all()
            )

        cod_items: list[dict[str, object]] = []
        cod_values: list[tuple[Decimal, str]] = []
        cod_incomplete = False
        for job, appointment, conversion, revision in scheduled_by_job.values():
            policy = self._resolve_term(policies, job.customer_id)
            if policy is None:
                cod_incomplete = True
                state = "INCOMPLETE"
                limitation = "No approved Company or Customer payment-term authority."
            elif policy.term_code not in ("COD", "DUE_ON_COMPLETION"):
                state = "NOT_DUE_TODAY"
                limitation = (
                    "Contractual terms do not require collection at completion."
                )
            elif conversion is None or revision is None:
                cod_incomplete = True
                state = "INCOMPLETE"
                limitation = "No accepted Estimate revision proves scheduled Job value."
            else:
                state = "QUALIFYING"
                limitation = None
                cod_values.append((revision.total_amount, revision.currency))
            cod_items.append(
                {
                    "job_id": job.id,
                    "job_number": job.job_number,
                    "appointment_id": appointment.id,
                    "appointment_number": appointment.appointment_number,
                    "branch_id": job.branch_id,
                    "customer_id": job.customer_id,
                    "scheduled_at": appointment.arrival_window_start_at,
                    "expected_amount": revision.total_amount if revision else None,
                    "currency": revision.currency if revision else None,
                    "evidence_basis": (
                        "ACCEPTED_ESTIMATE_REVISION" if revision else "UNAVAILABLE"
                    ),
                    "estimate_revision_id": revision.id if revision else None,
                    "payment_term_code": policy.term_code if policy else None,
                    "payment_term_net_days": policy.net_days if policy else None,
                    "payment_term_policy_id": policy.id if policy else None,
                    "payment_term_version": policy.version if policy else None,
                    "payment_term_source": policy.source_system if policy else None,
                    "payment_term_evidence_digest": (
                        policy.evidence_digest if policy else None
                    ),
                    "state": state,
                    "limitation": limitation,
                }
            )

        # Settlements currently have Company/provider scope but no Branch allocation.
        # Never attribute their fees or net amount to a selected Branch.
        settlement_rows: tuple[Settlement, ...] = ()
        settlement_limitation: str | None = None
        if branch_id is None and has_company_wide_branch_scope:
            settlement_rows = tuple(
                (
                    await session.scalars(
                        select(Settlement)
                        .where(
                            Settlement.company_id == company_id,
                            Settlement.settlement_date >= period_start,
                            Settlement.settlement_date <= period_end,
                        )
                        .order_by(Settlement.settlement_date.desc(), Settlement.id)
                    )
                ).all()
            )
        elif branch_id is not None:
            settlement_limitation = (
                "Provider settlement evidence is Company-scoped and cannot be "
                "truthfully allocated to a Branch."
            )
        else:
            settlement_limitation = (
                "Provider settlement evidence is Company-scoped and requires "
                "authorization to every Company Branch."
            )

        charged = _summarize_amounts(
            tuple(
                (receipt.captured_amount, receipt.currency)
                for receipt, _ in receipt_rows
            )
        )
        collected = _summarize_amounts(
            tuple(
                (receipt.captured_amount, receipt.currency)
                for receipt, _ in receipt_rows
            )
            + tuple((row.amount, row.currency) for row in manual_collection_rows)
        )
        refunds = _summarize_amounts(
            tuple(
                (receipt.refunded_amount, receipt.currency)
                for receipt, _ in receipt_rows
            )
        )
        disputes = _summarize_amounts(
            tuple(
                (receipt.disputed_amount, receipt.currency)
                for receipt, _ in receipt_rows
            )
        )
        settlement_evidence_limitation = settlement_limitation
        if not settlement_rows and settlement_evidence_limitation is None:
            settlement_evidence_limitation = (
                "No provider settlement or actual fee evidence is available for "
                "the selected period."
            )
        fees = _summarize_amounts(
            tuple((row.fee_amount, row.currency) for row in settlement_rows),
            unavailable=settlement_evidence_limitation,
        )
        settled_gross = _summarize_amounts(
            tuple((row.gross_amount, row.currency) for row in settlement_rows),
            unavailable=settlement_evidence_limitation,
        )
        settled_net = _summarize_amounts(
            tuple((row.net_amount, row.currency) for row in settlement_rows),
            unavailable=settlement_evidence_limitation,
        )
        due_today = _summarize_amounts(
            tuple((row.open_amount, row.currency) for row in invoice_rows)
        )

        fee_rate: Decimal | None = None
        if (
            fees.evidence_state == "AVAILABLE"
            and settled_gross.evidence_state == "AVAILABLE"
            and fees.amount is not None
            and settled_gross.amount
            and fees.currency == settled_gross.currency
        ):
            fee_rate = (fees.amount / settled_gross.amount).quantize(Decimal("0.0001"))

        cod = _summarize_amounts(tuple(cod_values))
        if cod_incomplete:
            cod = MoneyAmount(
                None,
                cod.currency,
                "INCOMPLETE",
                "One or more scheduled Jobs lack authoritative terms or value evidence.",
            )
        expected_total = compose_expected_collections(
            cod=ExpectedCollectionEvidence(
                cod.amount, cod.currency, cod.evidence_state, "SCHEDULED_COD"
            ),
            due_today=ExpectedCollectionEvidence(
                due_today.amount,
                due_today.currency,
                due_today.evidence_state,
                "OPEN_INVOICE_DUE_DATE",
            ),
        )

        return {
            "company_id": company_id,
            "branch_id": branch_id,
            "period_start": period_start,
            "period_end": period_end,
            "as_of": as_of,
            "generated_at": datetime.now(timezone.utc),
            "bank_balance": {
                "amount": None,
                "currency": None,
                "evidence_state": "UNAVAILABLE",
                "connection_state": "NOT_CONNECTED",
                "provider_as_of": None,
                "last_sync_at": None,
                "accounts": (),
                "limitation": "No sanctioned authoritative bank-balance source is connected.",
            },
            "accounts_receivable_due_today": {
                **asdict(due_today),
                "invoice_count": len(invoice_rows),
                "items": tuple(
                    {
                        "invoice_id": row.id,
                        "invoice_number": row.invoice_number,
                        "branch_id": row.branch_id,
                        "customer_id": row.customer_id,
                        "invoice_date": row.issue_date,
                        "due_date": row.due_date,
                        "terms": row.terms,
                        "open_balance": row.open_amount,
                        "currency": row.currency,
                    }
                    for row in invoice_rows
                ),
                "drilldown_path": f"/invoices?agingBucket=due_today&asOf={as_of.isoformat()}",
            },
            "cod_expected_today": {**asdict(cod), "items": tuple(cod_items)},
            "expected_collections_today": asdict(expected_total),
            "card_processing": {
                "transaction_count": len(receipt_rows),
                "amount_charged": asdict(charged),
                "refund_amount": asdict(refunds),
                "chargeback_amount": asdict(disputes),
                "fees_paid": asdict(fees),
                "effective_fee_rate": fee_rate,
                "transactions": tuple(
                    {
                        "receipt_id": receipt.id,
                        "intent_id": intent.id,
                        "branch_id": receipt.branch_id,
                        "customer_id": receipt.customer_id,
                        "invoice_id": intent.invoice_id,
                        "provider": intent.provider,
                        "provider_operation_id": intent.provider_operation_id,
                        "charged_amount": receipt.captured_amount,
                        "refunded_amount": receipt.refunded_amount,
                        "chargeback_amount": receipt.disputed_amount,
                        "currency": receipt.currency,
                        "collected_at": receipt.captured_at,
                        "settlement_state": "NOT_LINKED",
                        "deposit_state": "NOT_PROVEN",
                        "evidence_digest": receipt.evidence_digest,
                    }
                    for receipt, intent in receipt_rows
                ),
                "fee_evidence": tuple(
                    {
                        "settlement_id": row.id,
                        "provider": row.provider,
                        "provider_payout_id": row.provider_payout_id,
                        "settlement_date": row.settlement_date,
                        "gross_amount": row.gross_amount,
                        "fee_amount": row.fee_amount,
                        "net_amount": row.net_amount,
                        "currency": row.currency,
                        "reconciliation_state": row.status,
                        "evidence_digest": row.evidence_digest,
                    }
                    for row in settlement_rows
                ),
                "limitation": (
                    "Settlement fees are provider-payout evidence and are not allocated "
                    "to individual charges."
                ),
            },
            "collection_state": {
                "collected": asdict(collected),
                "collection_evidence": tuple(
                    {
                        "source_type": "PROVIDER_RECEIPT",
                        "source_id": receipt.id,
                        "branch_id": receipt.branch_id,
                        "customer_id": receipt.customer_id,
                        "invoice_id": intent.invoice_id,
                        "amount": receipt.captured_amount,
                        "currency": receipt.currency,
                        "occurred_at": receipt.captured_at,
                        "settlement_state": "NOT_LINKED",
                        "evidence_digest": receipt.evidence_digest,
                    }
                    for receipt, intent in receipt_rows
                )
                + tuple(
                    {
                        "source_type": "MANUAL_PAYMENT_EVIDENCE",
                        "source_id": row.id,
                        "branch_id": row.branch_id,
                        "customer_id": row.customer_id,
                        "invoice_id": row.invoice_id,
                        "amount": row.amount,
                        "currency": row.currency,
                        "occurred_at": row.occurred_at,
                        "settlement_state": "NOT_ASSERTED",
                        "evidence_digest": row.evidence_digest,
                    }
                    for row in manual_collection_rows
                ),
                "settled_gross": asdict(settled_gross),
                "settled_net": asdict(settled_net),
                "deposited": {
                    "amount": None,
                    "currency": None,
                    "evidence_state": "UNAVAILABLE",
                    "limitation": (
                        "ACP has deposit preparation records but no authoritative "
                        "bank-confirmed deposit timestamp or amount."
                    ),
                },
            },
        }


money_authority_service = MoneyAuthorityService()
