"""Provider-neutral bank evidence, matching, and reconciliation authority.

The module never posts journals or moves money. It validates sanitized source
evidence and persists only immutable/replay-safe bank-control facts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import (
    Account,
    BankAccount,
    BankReconciliation,
    BankTransaction,
    BankTransactionMatch,
    ControlAccountAssignment,
)
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.permissions.authorization import AuthorizationContext


class MatchState(StrEnum):
    MATCHED = "matched"
    UNMATCHED = "unmatched"
    AMBIGUOUS = "ambiguous"
    REVIEW_REQUIRED = "review_required"
    IGNORED = "ignored"
    TRANSFER_CANDIDATE = "transfer_candidate"
    RECONCILIATION_ONLY = "reconciliation_only"


@dataclass(frozen=True)
class NormalizedBankEvidence:
    external_transaction_id: str
    source_version: str
    source_digest: str
    acquired_at: datetime
    source_as_of: datetime
    posted_date: date
    effective_date: date | None
    amount: Decimal
    currency: str
    direction: str
    kind: str
    description: str
    memo: str | None = None
    state: str = "posted"


@dataclass(frozen=True)
class CanonicalMatchCandidate:
    target_type: str
    target_identity: str
    amount: Decimal
    currency: str
    effective_date: date
    explicit_bank_source_identity: str | None
    component_identities: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchDecision:
    state: MatchState
    target_type: str | None
    target_identity: str | None
    deterministic: bool
    reason_code: str
    candidates: tuple[CanonicalMatchCandidate, ...]


@dataclass(frozen=True)
class ReconciliationPreview:
    book_balance: Decimal
    cleared_total: Decimal
    outstanding_total: Decimal
    difference: Decimal
    status: str


def source_transition(
    *,
    existing_state: str,
    existing_digest: str,
    incoming_state: str,
    incoming_digest: str,
) -> str:
    if existing_digest == incoming_digest:
        return "idempotent_replay"
    if existing_state == "pending" and incoming_state == "posted":
        return "promote_to_posted"
    raise AccountingConflict("Posted bank transaction source identity replay drifted")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def normalize_evidence(evidence: NormalizedBankEvidence) -> NormalizedBankEvidence:
    if not evidence.external_transaction_id.strip():
        raise AccountingValidation("Bank source identity is required")
    if len(evidence.source_digest) != 64:
        raise AccountingValidation("Bank source digest must be SHA-256")
    if evidence.amount <= 0 or not evidence.amount.is_finite():
        raise AccountingValidation(
            "Bank transaction amount must be positive and finite"
        )
    if evidence.currency != evidence.currency.upper() or len(evidence.currency) != 3:
        raise AccountingValidation("Bank transaction currency must be ISO uppercase")
    if evidence.direction not in {"inflow", "outflow"}:
        raise AccountingValidation("Bank transaction direction is invalid")
    if evidence.kind not in {
        "deposit",
        "withdrawal",
        "check",
        "ach",
        "merchant_settlement",
        "fee",
        "interest",
        "refund",
        "reversal",
        "transfer",
        "payroll",
        "vendor_payment",
        "owner_movement",
        "other",
    }:
        raise AccountingValidation("Bank transaction kind is invalid")
    if evidence.state not in {"pending", "posted"}:
        raise AccountingValidation("Bank transaction state is invalid")
    return evidence


def deterministic_match(
    transaction: NormalizedBankEvidence,
    candidates: tuple[CanonicalMatchCandidate, ...],
) -> MatchDecision:
    """Auto-match only a unique exact candidate with explicit source linkage."""
    exact = tuple(
        candidate
        for candidate in candidates
        if candidate.amount == transaction.amount
        and candidate.currency == transaction.currency
        and candidate.effective_date
        == (transaction.effective_date or transaction.posted_date)
        and candidate.explicit_bank_source_identity
        == transaction.external_transaction_id
    )
    if len(exact) == 1:
        candidate = exact[0]
        return MatchDecision(
            MatchState.MATCHED,
            candidate.target_type,
            candidate.target_identity,
            True,
            "EXACT_EXPLICIT_SOURCE_LINK",
            exact,
        )
    if len(exact) > 1:
        return MatchDecision(
            MatchState.AMBIGUOUS,
            None,
            None,
            False,
            "MULTIPLE_EXACT_SOURCE_LINKS",
            exact,
        )
    similar = tuple(
        candidate
        for candidate in candidates
        if candidate.amount == transaction.amount
        and candidate.currency == transaction.currency
    )
    if similar:
        return MatchDecision(
            MatchState.REVIEW_REQUIRED,
            None,
            None,
            False,
            "VALUE_MATCH_WITHOUT_EXPLICIT_LINEAGE",
            similar,
        )
    return MatchDecision(MatchState.UNMATCHED, None, None, False, "NO_CANDIDATE", ())


def grouped_deposit_candidate(
    *,
    target_identity: str,
    external_transaction_id: str,
    currency: str,
    effective_date: date,
    components: tuple[tuple[str, Decimal], ...],
) -> CanonicalMatchCandidate:
    if len({identity for identity, _ in components}) != len(components):
        raise AccountingValidation("Grouped-deposit components must be unique")
    return CanonicalMatchCandidate(
        "grouped_deposit",
        target_identity,
        sum((amount for _, amount in components), Decimal(0)),
        currency,
        effective_date,
        external_transaction_id,
        tuple(identity for identity, _ in components),
    )


def transfer_control(
    *,
    source_account_id: UUID,
    destination_account_id: UUID,
    source_amount: Decimal,
    destination_amount: Decimal,
) -> dict[str, object]:
    if source_account_id == destination_account_id:
        raise AccountingValidation("A bank transfer requires two distinct accounts")
    if (
        source_amount <= 0
        or destination_amount <= 0
        or source_amount != destination_amount
    ):
        return {
            "state": "review_required",
            "income_expense_effect": None,
            "reason": "Transfer legs must be equal and opposite.",
        }
    return {
        "state": "matched",
        "income_expense_effect": Decimal(0),
        "reason": "Inter-account transfer is balance-sheet neutral.",
    }


def control_integrity(
    *,
    bank_delta: Decimal,
    cash_gl_delta: Decimal,
    undeposited_clearing: Decimal = Decimal(0),
    merchant_clearing: Decimal = Decimal(0),
) -> dict[str, object]:
    explained = cash_gl_delta + undeposited_clearing + merchant_clearing
    difference = bank_delta - explained
    return {
        "state": "matched" if difference == 0 else "review_required",
        "difference": difference,
        "double_recognition_guard": (
            "Grouped deposits clear control accounts and never create revenue."
        ),
    }


def reconciliation_preview(
    *,
    ending_balance: Decimal,
    book_balance: Decimal,
    cleared_total: Decimal,
    outstanding_total: Decimal,
    unresolved_count: int,
) -> ReconciliationPreview:
    difference = ending_balance - (book_balance + cleared_total - outstanding_total)
    status = (
        "ready_to_close"
        if difference == 0 and unresolved_count == 0
        else "review_required"
    )
    return ReconciliationPreview(
        book_balance, cleared_total, outstanding_total, difference, status
    )


class BankAuthorityService:
    async def create_account(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        ledger_account_id: UUID,
        institution_name: str,
        account_name: str,
        account_type: str,
        masked_identity: str,
        currency: str,
        source_system: str,
        source_account_id: str,
        source_version: str,
        source_digest: str,
        source_as_of: datetime,
        opening_balance: Decimal | None = None,
        opening_balance_date: date | None = None,
        opening_balance_provenance: dict[str, object] | None = None,
    ) -> BankAccount:
        ledger = await session.scalar(
            select(Account).where(
                Account.company_id == context.company.id,
                Account.id == ledger_account_id,
            )
        )
        if ledger is None:
            raise AccountingNotFound("Mapped bank/cash account was not found")
        control = await session.scalar(
            select(ControlAccountAssignment.id).where(
                ControlAccountAssignment.company_id == context.company.id,
                ControlAccountAssignment.account_id == ledger_account_id,
                ControlAccountAssignment.control_role == "bank_cash",
                ControlAccountAssignment.effective_from <= source_as_of.date(),
                (
                    ControlAccountAssignment.effective_to.is_(None)
                    | (ControlAccountAssignment.effective_to >= source_as_of.date())
                ),
            )
        )
        if control is None:
            raise AccountingValidation(
                "Bank authority requires a mapped bank/cash control account"
            )
        if opening_balance is not None and (
            opening_balance_date is None or not opening_balance_provenance
        ):
            raise AccountingValidation("Opening balance requires dated provenance")
        existing = await session.scalar(
            select(BankAccount).where(
                BankAccount.company_id == context.company.id,
                BankAccount.source_system == source_system,
                BankAccount.source_account_id == source_account_id,
            )
        )
        if existing is not None:
            if existing.source_digest != source_digest:
                raise AccountingConflict("Bank account source identity replay drifted")
            return existing
        record = BankAccount(
            company_id=context.company.id,
            ledger_account_id=ledger_account_id,
            institution_name=institution_name.strip(),
            account_name=account_name.strip(),
            account_type=account_type,
            masked_identity=masked_identity.strip(),
            currency=currency,
            source_system=source_system,
            source_account_id=source_account_id,
            source_version=source_version,
            source_digest=source_digest,
            source_as_of=source_as_of,
            opening_balance=opening_balance,
            opening_balance_date=opening_balance_date,
            opening_balance_provenance=opening_balance_provenance or {},
            created_by_user_id=context.user.id,
        )
        session.add(record)
        await session.flush()
        self._audit(
            session,
            context,
            "accounting.bank_account.created",
            "bank_account",
            record.id,
        )
        return record

    async def ingest(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bank_account_id: UUID,
        source_system: str,
        evidence: NormalizedBankEvidence,
    ) -> BankTransaction:
        evidence = normalize_evidence(evidence)
        account = await session.scalar(
            select(BankAccount).where(
                BankAccount.company_id == context.company.id,
                BankAccount.id == bank_account_id,
            )
        )
        if account is None:
            raise AccountingNotFound("Bank account was not found")
        if account.currency != evidence.currency:
            raise AccountingValidation("Transaction currency differs from bank account")
        existing = await session.scalar(
            select(BankTransaction)
            .where(
                BankTransaction.company_id == context.company.id,
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.source_system == source_system,
                BankTransaction.external_transaction_id
                == evidence.external_transaction_id,
            )
            .with_for_update()
        )
        if existing is not None:
            transition = source_transition(
                existing_state=existing.state,
                existing_digest=existing.source_digest,
                incoming_state=evidence.state,
                incoming_digest=evidence.source_digest,
            )
            if transition == "idempotent_replay":
                return existing
            if (
                transition == "promote_to_posted"
                and evidence.source_as_of >= existing.source_as_of
            ):
                existing.prior_source_digest = existing.source_digest
                existing.source_digest = evidence.source_digest
                existing.source_version = evidence.source_version
                existing.source_as_of = evidence.source_as_of
                existing.acquired_at = evidence.acquired_at
                existing.posted_date = evidence.posted_date
                existing.effective_date = evidence.effective_date
                existing.amount = evidence.amount
                existing.direction = evidence.direction
                existing.kind = evidence.kind
                existing.description = evidence.description
                existing.memo = evidence.memo
                existing.state = "posted"
                existing.updated_at = datetime.now(timezone.utc)
                self._audit(
                    session,
                    context,
                    "accounting.bank_transaction.posted",
                    "bank_transaction",
                    existing.id,
                )
                return existing
            raise AccountingConflict(
                "Posted bank transaction source identity replay drifted"
            )
        transaction = BankTransaction(
            company_id=context.company.id,
            bank_account_id=bank_account_id,
            source_system=source_system,
            external_transaction_id=evidence.external_transaction_id,
            source_version=evidence.source_version,
            source_digest=evidence.source_digest,
            acquired_at=evidence.acquired_at,
            source_as_of=evidence.source_as_of,
            posted_date=evidence.posted_date,
            effective_date=evidence.effective_date,
            amount=evidence.amount,
            currency=evidence.currency,
            direction=evidence.direction,
            kind=evidence.kind,
            description=evidence.description,
            memo=evidence.memo,
            state=evidence.state,
        )
        session.add(transaction)
        await session.flush()
        self._audit(
            session,
            context,
            "accounting.bank_transaction.ingested",
            "bank_transaction",
            transaction.id,
        )
        return transaction

    async def record_match(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bank_transaction_id: UUID,
        decision: MatchDecision,
    ) -> BankTransactionMatch:
        transaction = await session.scalar(
            select(BankTransaction).where(
                BankTransaction.company_id == context.company.id,
                BankTransaction.id == bank_transaction_id,
            )
        )
        if transaction is None:
            raise AccountingNotFound("Bank transaction was not found")
        payload = [asdict(candidate) for candidate in decision.candidates]
        decision_digest = _digest(
            {"transaction": transaction.source_digest, "decision": asdict(decision)}
        )
        existing = await session.scalar(
            select(BankTransactionMatch)
            .where(
                BankTransactionMatch.company_id == context.company.id,
                BankTransactionMatch.bank_transaction_id == transaction.id,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.evidence_digest == decision_digest:
                return existing
            raise AccountingConflict("Bank transaction match decision already exists")
        record = BankTransactionMatch(
            company_id=context.company.id,
            bank_transaction_id=transaction.id,
            state=decision.state.value,
            target_type=decision.target_type,
            target_identity=decision.target_identity,
            candidate_evidence=payload,
            deterministic=decision.deterministic,
            reason_code=decision.reason_code,
            evidence_digest=decision_digest,
            decided_by_user_id=None if decision.deterministic else context.user.id,
        )
        session.add(record)
        await session.flush()
        self._audit(
            session,
            context,
            "accounting.bank_transaction.matched",
            "bank_transaction_match",
            record.id,
        )
        return record

    async def close_reconciliation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bank_account_id: UUID,
        statement_identity: str,
        period_start: date,
        period_end: date,
        ending_balance: Decimal,
        book_balance: Decimal,
        cleared_total: Decimal,
        outstanding_total: Decimal,
        cleared_transaction_ids: tuple[UUID, ...],
        outstanding_items: list[dict[str, object]],
        source_evidence: dict[str, object],
        preparer_user_id: UUID,
    ) -> BankReconciliation:
        if preparer_user_id == context.user.id:
            raise AccountingConflict(
                "Reconciliation preparer and reviewer must be distinct"
            )
        statement_source_digest = source_evidence.get("source_digest")
        if (
            not isinstance(statement_source_digest, str)
            or len(statement_source_digest) != 64
        ):
            raise AccountingValidation(
                "Statement source evidence requires a SHA-256 digest"
            )
        account = await session.scalar(
            select(BankAccount).where(
                BankAccount.company_id == context.company.id,
                BankAccount.id == bank_account_id,
            )
        )
        if account is None:
            raise AccountingNotFound("Bank account was not found")
        preview = reconciliation_preview(
            ending_balance=ending_balance,
            book_balance=book_balance,
            cleared_total=cleared_total,
            outstanding_total=outstanding_total,
            unresolved_count=sum(
                1 for item in outstanding_items if item.get("state") != "explained"
            ),
        )
        if preview.status != "ready_to_close":
            raise AccountingConflict(
                "Bank reconciliation difference must be zero with no unresolved items"
            )
        transaction_count = await session.scalar(
            select(func.count(BankTransaction.id)).where(
                BankTransaction.company_id == context.company.id,
                BankTransaction.bank_account_id == bank_account_id,
                BankTransaction.id.in_(cleared_transaction_ids),
                BankTransaction.state == "posted",
                BankTransaction.posted_date <= period_end,
            )
        )
        if transaction_count != len(cleared_transaction_ids):
            raise AccountingConflict(
                "Cleared transaction is not posted in the reconciliation scope"
            )
        digest_payload: dict[str, Any] = {
            "account": str(bank_account_id),
            "statement": statement_identity,
            "period": [period_start.isoformat(), period_end.isoformat()],
            "ending_balance": str(ending_balance),
            "cleared": sorted(str(value) for value in cleared_transaction_ids),
            "outstanding": outstanding_items,
            "source": source_evidence,
        }
        reconciliation_digest = _digest(digest_payload)
        existing = await session.scalar(
            select(BankReconciliation)
            .where(
                BankReconciliation.company_id == context.company.id,
                BankReconciliation.bank_account_id == bank_account_id,
                BankReconciliation.statement_identity == statement_identity,
            )
            .with_for_update()
        )
        if existing is not None:
            if existing.evidence_digest == reconciliation_digest:
                return existing
            raise AccountingConflict("Closed bank reconciliation is immutable")
        record = BankReconciliation(
            company_id=context.company.id,
            bank_account_id=bank_account_id,
            statement_identity=statement_identity,
            period_start=period_start,
            period_end=period_end,
            ending_balance=ending_balance,
            book_balance=book_balance,
            cleared_total=cleared_total,
            outstanding_total=outstanding_total,
            difference=preview.difference,
            status="closed",
            cleared_transaction_ids=[str(value) for value in cleared_transaction_ids],
            outstanding_items=outstanding_items,
            source_evidence=source_evidence,
            evidence_digest=reconciliation_digest,
            preparer_user_id=preparer_user_id,
            reviewer_user_id=context.user.id,
            closed_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.flush()
        self._audit(
            session,
            context,
            "accounting.bank_reconciliation.closed",
            "bank_reconciliation",
            record.id,
        )
        return record

    @staticmethod
    def _audit(
        session: AsyncSession,
        context: AuthorizationContext,
        action: str,
        resource_type: str,
        resource_id: UUID,
    ) -> None:
        AuditService.stage(
            session,
            AuditEntry(
                action=action,
                outcome="success",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                resource_type=resource_type,
                resource_id=resource_id,
            ),
        )


bank_authority_service = BankAuthorityService()
