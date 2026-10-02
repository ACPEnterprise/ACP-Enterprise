"""Canonical source-domain projections for bank-transaction matching.

The adapters are read-only. They expose already-authoritative evidence to the
bank matcher and never create payment, payroll, AP, transfer, or journal truth.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.banking import CanonicalMatchCandidate
from app.accounting.models import (
    BankAccount,
    ControlAccountAssignment,
    Journal,
    JournalLine,
)
from app.accounts_payable.models import Disbursement
from app.payments.models import (
    Deposit,
    DepositReceipt,
    PaymentIntent,
    PaymentReceipt,
    ReceiptEvent,
    Refund,
    Settlement,
)
from app.payroll.models import (
    PayrollPaymentExecutionItemRecord,
    PayrollPaymentExecutionRecord,
    PayrollPaymentInstructionRecord,
)


def _candidate(
    *,
    target_type: str,
    target_identity: str,
    amount: Decimal,
    currency: str,
    effective_date: date,
    bank_identity: str | None,
    source_system: str,
    source_digest: str,
    components: tuple[str, ...] = (),
    deterministic: bool = True,
    direction: str | None = None,
) -> CanonicalMatchCandidate:
    return CanonicalMatchCandidate(
        target_type=target_type,
        target_identity=target_identity,
        amount=amount,
        currency=currency,
        effective_date=effective_date,
        explicit_bank_source_identity=bank_identity if deterministic else None,
        component_identities=components,
        source_system=source_system,
        source_digest=source_digest,
        evidence_strength=("exact_source_lineage" if deterministic else "structured_review"),
        expected_direction=direction,
    )


def customer_payment_candidate(
    receipt: PaymentReceipt,
    intent: PaymentIntent,
    applications: tuple[str, ...] = (),
) -> CanonicalMatchCandidate:
    return _candidate(
        target_type="customer_payment",
        target_identity=f"payment_receipt:{receipt.id}",
        amount=receipt.captured_amount,
        currency=receipt.currency,
        effective_date=receipt.captured_at.date(),
        bank_identity=intent.provider_operation_id,
        source_system=f"payments:{intent.provider}",
        source_digest=receipt.evidence_digest,
        components=applications,
        deterministic=intent.provider_operation_id is not None,
        direction="inflow",
    )


def grouped_deposit_projection(
    deposit: Deposit, components: tuple[str, ...]
) -> CanonicalMatchCandidate:
    return _candidate(
        target_type="grouped_deposit",
        target_identity=f"payment_deposit:{deposit.id}",
        amount=deposit.gross_amount,
        currency=deposit.currency,
        effective_date=deposit.created_at.date(),
        bank_identity=deposit.destination_reference,
        source_system="payments",
        source_digest=deposit.evidence_digest,
        components=components,
        deterministic=bool(components),
        direction="inflow",
    )


def merchant_settlement_candidates(
    settlement: Settlement,
) -> tuple[CanonicalMatchCandidate, ...]:
    components = (
        f"gross:{settlement.gross_amount}",
        f"refund:{settlement.refund_amount}",
        f"dispute:{settlement.dispute_amount}",
        f"fee:{settlement.fee_amount}",
        f"adjustment:{settlement.adjustment_amount}",
    )
    result = [
        _candidate(
            target_type="merchant_settlement",
            target_identity=f"payment_settlement:{settlement.id}",
            amount=settlement.net_amount,
            currency=settlement.currency,
            effective_date=settlement.settlement_date,
            bank_identity=settlement.provider_payout_id,
            source_system=f"payments:{settlement.provider}",
            source_digest=settlement.evidence_digest,
            components=components,
            direction="inflow",
        )
    ]
    if settlement.fee_amount > 0:
        result.append(
            _candidate(
                target_type="merchant_fee",
                target_identity=f"payment_settlement_fee:{settlement.id}",
                amount=settlement.fee_amount,
                currency=settlement.currency,
                effective_date=settlement.settlement_date,
                bank_identity=settlement.provider_payout_id,
                source_system=f"payments:{settlement.provider}",
                source_digest=settlement.evidence_digest,
                components=(f"payment_settlement:{settlement.id}",),
                direction="outflow",
            )
        )
    return tuple(result)


def merchant_refund_candidate(
    refund: Refund, intent: PaymentIntent
) -> CanonicalMatchCandidate:
    return _candidate(
        target_type="merchant_refund",
        target_identity=f"payment_refund:{refund.id}",
        amount=refund.amount,
        currency=refund.currency,
        effective_date=refund.created_at.date(),
        bank_identity=refund.provider_operation_id,
        source_system=f"payments:{intent.provider}",
        source_digest=refund.evidence_digest or refund.request_digest,
        components=(f"payment_receipt:{refund.receipt_id}",),
        deterministic=(
            refund.status == "succeeded"
            and refund.provider_operation_id is not None
            and refund.evidence_digest is not None
        ),
        direction="outflow",
    )


def vendor_payment_candidate(row: Disbursement) -> CanonicalMatchCandidate:
    return _candidate(
        target_type=(
            "vendor_check"
            if row.method_category.lower() in {"check", "paper_check"}
            else "vendor_payment"
        ),
        target_identity=f"ap_disbursement:{row.id}",
        amount=row.amount,
        currency=row.currency,
        effective_date=row.effective_date,
        bank_identity=row.source_identity,
        source_system=f"accounts_payable:{row.source_system}",
        source_digest=row.evidence_digest,
        components=(row.external_reference,),
        direction="outflow",
    )


def payroll_payment_candidate(
    item: PayrollPaymentExecutionItemRecord,
    instruction: PayrollPaymentInstructionRecord,
    execution: PayrollPaymentExecutionRecord,
) -> CanonicalMatchCandidate:
    return _candidate(
        target_type=(
            "payroll_check"
            if instruction.method_type == "paper_check"
            else "payroll_withdrawal"
        ),
        target_identity=f"payroll_execution_item:{item.id}",
        amount=item.amount,
        currency=item.currency,
        effective_date=execution.authorized_at.date(),
        bank_identity=item.provider_safe_reference,
        source_system=f"payroll:{execution.provider_identity}",
        source_digest=item.evidence_digest or execution.execution_digest,
        components=(f"payroll_execution:{execution.id}",),
        deterministic=(
            item.lifecycle == "settled"
            and item.provider_safe_reference is not None
            and item.evidence_digest is not None
        ),
        direction="outflow",
    )


def accounting_movement_candidate(
    journal: Journal, line: JournalLine, transfer_paired: bool = True
) -> CanonicalMatchCandidate:
    amount = line.debit if line.debit > 0 else line.credit
    is_owner = journal.source_type in {
        "owner_contribution",
        "owner_distribution",
    }
    return _candidate(
        target_type=journal.source_type,
        target_identity=f"accounting_journal:{journal.id}",
        amount=amount,
        currency=journal.currency,
        effective_date=journal.effective_date,
        bank_identity=journal.source_identity,
        source_system=f"accounting:{journal.source_system}",
        source_digest=journal.source_digest,
        components=(f"journal_line:{line.id}",),
        deterministic=(not is_owner and (journal.source_type != "bank_transfer" or transfer_paired)),
        direction="inflow" if line.debit > 0 else "outflow",
    )


class BankMatchCandidateAdapterService:
    """Build Company-scoped candidates from canonical source authorities."""

    async def customer_payments(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        rows = tuple(
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
                        PaymentReceipt.currency == currency,
                        PaymentReceipt.captured_at >= period_start,
                        PaymentReceipt.captured_at < period_end.fromordinal(
                            period_end.toordinal() + 1
                        ),
                        PaymentIntent.status == "captured",
                    )
                )
            ).all()
        )
        receipt_ids = tuple(receipt.id for receipt, _ in rows)
        applications: dict[UUID, list[str]] = {}
        if receipt_ids:
            events = tuple(
                (
                    await session.scalars(
                        select(ReceiptEvent).where(
                            ReceiptEvent.company_id == company_id,
                            ReceiptEvent.receipt_id.in_(receipt_ids),
                            ReceiptEvent.event_type == "application_observed",
                        )
                    )
                ).all()
            )
            for event in events:
                if event.invoice_id is not None:
                    applications.setdefault(event.receipt_id, []).append(
                        f"invoice_application:{event.invoice_id}:{event.amount}"
                    )
        return tuple(
            customer_payment_candidate(
                receipt,
                intent,
                tuple(sorted(applications.get(receipt.id, ()))),
            )
            for receipt, intent in rows
        )

    async def grouped_deposits(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        deposits = tuple(
            (
                await session.scalars(
                    select(Deposit).where(
                        Deposit.company_id == company_id,
                        Deposit.currency == currency,
                        Deposit.created_at >= period_start,
                        Deposit.created_at
                        < period_end.fromordinal(period_end.toordinal() + 1),
                        Deposit.status.in_(("submitted", "approved", "deposited")),
                    )
                )
            ).all()
        )
        if not deposits:
            return ()
        links = tuple(
            (
                await session.scalars(
                    select(DepositReceipt).where(
                        DepositReceipt.company_id == company_id,
                        DepositReceipt.deposit_id.in_(tuple(row.id for row in deposits)),
                    )
                )
            ).all()
        )
        components: dict[UUID, list[str]] = {}
        for link in links:
            components.setdefault(link.deposit_id, []).append(
                f"payment_receipt:{link.receipt_id}"
            )
        return tuple(
            grouped_deposit_projection(
                row, tuple(sorted(components.get(row.id, ())))
            )
            for row in deposits
        )

    async def merchant_settlements(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        rows = tuple(
            (
                await session.scalars(
                    select(Settlement).where(
                        Settlement.company_id == company_id,
                        Settlement.currency == currency,
                        Settlement.settlement_date.between(period_start, period_end),
                        Settlement.status == "received",
                    )
                )
            ).all()
        )
        return tuple(
            candidate
            for row in rows
            for candidate in merchant_settlement_candidates(row)
        )

    async def merchant_refunds(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        rows = tuple(
            (
                await session.execute(
                    select(Refund, PaymentIntent)
                    .join(
                        PaymentReceipt,
                        (PaymentReceipt.company_id == Refund.company_id)
                        & (PaymentReceipt.id == Refund.receipt_id),
                    )
                    .join(
                        PaymentIntent,
                        (PaymentIntent.company_id == PaymentReceipt.company_id)
                        & (PaymentIntent.id == PaymentReceipt.intent_id),
                    )
                    .where(
                        Refund.company_id == company_id,
                        Refund.currency == currency,
                        Refund.created_at >= period_start,
                        Refund.created_at
                        < period_end.fromordinal(period_end.toordinal() + 1),
                        Refund.status.in_(("succeeded", "reconciliation_required")),
                    )
                )
            ).all()
        )
        return tuple(merchant_refund_candidate(*row) for row in rows)

    async def vendor_payments(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        rows = tuple(
            (
                await session.scalars(
                    select(Disbursement).where(
                        Disbursement.company_id == company_id,
                        Disbursement.currency == currency,
                        Disbursement.effective_date.between(period_start, period_end),
                        Disbursement.status.in_(("recorded", "posted", "paid")),
                    )
                )
            ).all()
        )
        return tuple(vendor_payment_candidate(row) for row in rows)

    async def payroll_payments(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        currency: str,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        rows = tuple(
            (
                await session.execute(
                    select(
                        PayrollPaymentExecutionItemRecord,
                        PayrollPaymentInstructionRecord,
                        PayrollPaymentExecutionRecord,
                    )
                    .join(
                        PayrollPaymentExecutionRecord,
                        PayrollPaymentExecutionRecord.id
                        == PayrollPaymentExecutionItemRecord.execution_id,
                    )
                    .join(
                        PayrollPaymentInstructionRecord,
                        PayrollPaymentInstructionRecord.id
                        == PayrollPaymentExecutionItemRecord.instruction_id,
                    )
                    .where(
                        PayrollPaymentExecutionItemRecord.company_id == company_id,
                        PayrollPaymentExecutionItemRecord.currency == currency,
                        PayrollPaymentExecutionRecord.authorized_at >= period_start,
                        PayrollPaymentExecutionRecord.authorized_at
                        < period_end.fromordinal(period_end.toordinal() + 1),
                        PayrollPaymentExecutionRecord.lifecycle.in_(
                            ("provider_acknowledged", "settlement_pending", "partially_settled", "settled")
                        ),
                        PayrollPaymentExecutionItemRecord.lifecycle.in_(
                            ("acknowledged", "settlement_pending", "settled")
                        ),
                    )
                )
            ).all()
        )
        return tuple(payroll_payment_candidate(*row) for row in rows)

    async def accounting_movements(
        self,
        session: AsyncSession,
        *,
        bank_account: BankAccount,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        paired_bank_leg = (
            select(JournalLine.id)
            .join(
                ControlAccountAssignment,
                (ControlAccountAssignment.company_id == JournalLine.company_id)
                & (ControlAccountAssignment.account_id == JournalLine.account_id)
                & (ControlAccountAssignment.control_role == "bank_cash"),
            )
            .where(
                JournalLine.company_id == Journal.company_id,
                JournalLine.journal_id == Journal.id,
                JournalLine.account_id != bank_account.ledger_account_id,
            )
            .correlate(Journal)
            .exists()
        )
        rows = tuple(
            (
                await session.execute(
                    select(Journal, JournalLine, paired_bank_leg)
                    .join(
                        JournalLine,
                        (JournalLine.company_id == Journal.company_id)
                        & (JournalLine.journal_id == Journal.id),
                    )
                    .where(
                        Journal.company_id == bank_account.company_id,
                        Journal.status == "posted",
                        Journal.currency == bank_account.currency,
                        Journal.effective_date.between(period_start, period_end),
                        JournalLine.account_id == bank_account.ledger_account_id,
                        Journal.source_type.in_(
                            (
                                "bank_transfer",
                                "owner_contribution",
                                "owner_distribution",
                                "payroll_liability_payment",
                                "payroll_tax_payment",
                            )
                        ),
                    )
                )
            ).all()
        )
        return tuple(accounting_movement_candidate(*row) for row in rows)

    async def all_candidates(
        self,
        session: AsyncSession,
        *,
        bank_account: BankAccount,
        period_start: date,
        period_end: date,
    ) -> tuple[CanonicalMatchCandidate, ...]:
        return (
            *(
                await self.customer_payments(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.grouped_deposits(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.merchant_settlements(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.merchant_refunds(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.vendor_payments(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.payroll_payments(
                    session,
                    company_id=bank_account.company_id,
                    currency=bank_account.currency,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
            *(
                await self.accounting_movements(
                    session,
                    bank_account=bank_account,
                    period_start=period_start,
                    period_end=period_end,
                )
            ),
        )


bank_match_candidate_adapters = BankMatchCandidateAdapterService()
