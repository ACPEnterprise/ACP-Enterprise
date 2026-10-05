"""Operator read/command projections over canonical Banking authority."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.banking import (
    NormalizedBankEvidence,
    bank_authority_service,
    normalize_evidence,
)
from app.accounting.banking_schemas import (
    BankAccountResponse,
    BankAccountSummary,
    BankDrilldownResponse,
    BankImportConfirmRequest,
    BankImportConfirmResponse,
    BankImportDisposition,
    BankImportPreviewRequest,
    BankImportPreviewResponse,
    BankMatchReviewItem,
    BankReconciliationPreviewRequest,
    BankReconciliationPreviewResponse,
    BankReconciliationResponse,
    BankTransactionResponse,
    CashFlowResponse,
    CashFlowSection,
)
from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import (
    BankAccount,
    BankAccountGLMapping,
    BankBalanceEvidence,
    BankConnection,
    BankReconciliation,
    BankTransaction,
    BankTransactionMatch,
    Journal,
    JournalLine,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _signed(direction: str, amount: Decimal) -> Decimal:
    return amount if direction == "inflow" else -amount


class BankingOperatorService:
    async def reconciliation_response(
        self, session: AsyncSession, row: BankReconciliation
    ) -> BankReconciliationResponse:
        preparer = await session.get(User, row.preparer_user_id)
        reviewer = (
            await session.get(User, row.reviewer_user_id)
            if row.reviewer_user_id is not None
            else None
        )
        values = {
            column.name: getattr(row, column.name)
            for column in BankReconciliation.__table__.columns
        }
        values["prepared_by"] = {
            "display_name": preparer.display_name if preparer else "Unavailable user",
            "occurred_at": row.submitted_at or row.prepared_at,
        }
        values["reviewed_by"] = (
            {
                "display_name": reviewer.display_name,
                "occurred_at": row.closed_at,
            }
            if reviewer is not None and row.closed_at is not None
            else None
        )
        return BankReconciliationResponse.model_validate(values)

    async def _account(
        self, session: AsyncSession, company_id: UUID, account_id: UUID
    ) -> BankAccount:
        account = await session.scalar(
            select(BankAccount).where(
                BankAccount.company_id == company_id,
                BankAccount.id == account_id,
            )
        )
        if account is None:
            raise AccountingNotFound("Bank account was not found")
        return account

    async def summaries(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        accessible_branch_ids: frozenset[UUID] | None = None,
    ) -> tuple[BankAccountSummary, ...]:
        scope = [BankAccount.company_id == company_id]
        if accessible_branch_ids is not None:
            scope.append(
                BankAccount.branch_id.is_(None)
                | BankAccount.branch_id.in_(accessible_branch_ids)
            )
        accounts = tuple(
            (
                await session.scalars(
                    select(BankAccount).where(*scope).order_by(BankAccount.account_name)
                )
            ).all()
        )
        result: list[BankAccountSummary] = []
        for account in accounts:
            transactions = tuple(
                (
                    await session.scalars(
                        select(BankTransaction).where(
                            BankTransaction.company_id == company_id,
                            BankTransaction.bank_account_id == account.id,
                        )
                    )
                ).all()
            )
            matches = tuple(
                (
                    await session.scalars(
                        select(BankTransactionMatch)
                        .join(
                            BankTransaction,
                            BankTransaction.id
                            == BankTransactionMatch.bank_transaction_id,
                        )
                        .where(
                            BankTransactionMatch.company_id == company_id,
                            BankTransaction.bank_account_id == account.id,
                        )
                    )
                ).all()
            )
            counts = Counter(row.state for row in matches)
            matched_ids = {row.bank_transaction_id for row in matches}
            latest = await session.scalar(
                select(BankReconciliation)
                .where(
                    BankReconciliation.company_id == company_id,
                    BankReconciliation.bank_account_id == account.id,
                    BankReconciliation.status == "closed",
                )
                .order_by(BankReconciliation.period_end.desc())
                .limit(1)
            )
            active = await session.scalar(
                select(BankReconciliation)
                .where(
                    BankReconciliation.company_id == company_id,
                    BankReconciliation.bank_account_id == account.id,
                    BankReconciliation.status != "closed",
                )
                .order_by(BankReconciliation.prepared_at.desc())
                .limit(1)
            )
            connection = (
                await session.get(BankConnection, account.connection_id)
                if account.connection_id
                else None
            )
            mapping = await session.scalar(
                select(BankAccountGLMapping).where(
                    BankAccountGLMapping.company_id == company_id,
                    BankAccountGLMapping.bank_account_id == account.id,
                    BankAccountGLMapping.status == "approved",
                )
            )
            balance = await session.scalar(
                select(BankBalanceEvidence)
                .where(
                    BankBalanceEvidence.company_id == company_id,
                    BankBalanceEvidence.bank_account_id == account.id,
                )
                .order_by(BankBalanceEvidence.balance_as_of.desc())
                .limit(1)
            )
            result.append(
                BankAccountSummary(
                    account=BankAccountResponse.model_validate(account),
                    imported_count=len(transactions),
                    matched_count=counts["matched"],
                    unmatched_count=sum(
                        1 for row in transactions if row.id not in matched_ids
                    )
                    + counts["unmatched"],
                    review_required_count=counts["review_required"]
                    + counts["ambiguous"],
                    transfer_candidate_count=counts["transfer_candidate"],
                    active_reconciliation_state=active.status if active else "none",
                    current_difference=active.difference if active else None,
                    last_reconciled_through=latest.period_end if latest else None,
                    latest_closed_reconciliation=(
                        await self.reconciliation_response(session, latest)
                        if latest
                        else None
                    ),
                    connection_status=connection.status if connection else "manual",
                    mapping_state=mapping.status if mapping else "unmapped",
                    current_balance=balance.current_balance if balance else None,
                    available_balance=balance.available_balance if balance else None,
                    balance_as_of=balance.balance_as_of if balance else None,
                )
            )
        return tuple(result)

    async def preview_import(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        account_id: UUID,
        request: BankImportPreviewRequest,
    ) -> BankImportPreviewResponse:
        await self._account(session, company_id, account_id)
        identities = [
            (row.source_system, row.external_transaction_id)
            for row in request.transactions
        ]
        duplicates = Counter(identities)
        existing = {
            (row.source_system, row.external_transaction_id): row
            for row in (
                await session.scalars(
                    select(BankTransaction).where(
                        BankTransaction.company_id == company_id,
                        BankTransaction.bank_account_id == account_id,
                        BankTransaction.external_transaction_id.in_(
                            tuple(identity for _, identity in identities)
                        ),
                    )
                )
            ).all()
        }
        dispositions: list[BankImportDisposition] = []
        for row in request.transactions:
            disposition, reason = "new", "New source identity."
            try:
                normalize_evidence(
                    NormalizedBankEvidence(**row.model_dump(exclude={"source_system"}))
                )
            except AccountingValidation as error:
                disposition, reason = "invalid", str(error)
            else:
                identity = (row.source_system, row.external_transaction_id)
                prior = existing.get(identity)
                if duplicates[identity] > 1:
                    disposition, reason = "duplicate", "Repeated in this batch."
                elif prior and prior.source_digest == row.source_digest:
                    disposition, reason = (
                        "replay",
                        "Identical evidence is already stored.",
                    )
                elif prior:
                    disposition, reason = "conflict", "Source identity digest changed."
            dispositions.append(
                BankImportDisposition(
                    source_system=row.source_system,
                    source_identity=row.external_transaction_id,
                    disposition=disposition,
                    reason=reason,
                )
            )
        payload = request.model_dump(mode="json") | {
            "bank_account_id": str(account_id),
            "company_id": str(company_id),
        }
        counts = Counter(row.disposition for row in dispositions)
        return BankImportPreviewResponse(
            bank_account_id=account_id,
            **request.model_dump(exclude={"transactions"}),
            transaction_count=len(request.transactions),
            new_count=counts["new"],
            replay_count=counts["replay"],
            duplicate_count=counts["duplicate"],
            conflict_count=counts["conflict"],
            invalid_count=counts["invalid"],
            preview_digest=_digest(payload),
            dispositions=tuple(dispositions),
        )

    async def confirm_import(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        account_id: UUID,
        request: BankImportConfirmRequest,
    ) -> BankImportConfirmResponse:
        preview_request = BankImportPreviewRequest.model_validate(
            request.model_dump(exclude={"preview_digest"})
        )
        preview = await self.preview_import(
            session,
            company_id=context.company.id,
            account_id=account_id,
            request=preview_request,
        )
        if preview.preview_digest != request.preview_digest:
            raise AccountingConflict("Import preview evidence changed before confirm")
        dispositions: list[BankImportDisposition] = []
        persisted = replayed = quarantined = 0
        by_identity = {
            (row.source_system, row.source_identity): row
            for row in preview.dispositions
        }
        for row in request.transactions:
            disposition = by_identity[(row.source_system, row.external_transaction_id)]
            if disposition.disposition in {"conflict", "duplicate", "invalid"}:
                quarantined += 1
                dispositions.append(disposition)
                continue
            await bank_authority_service.ingest(
                session,
                context=context,
                bank_account_id=account_id,
                source_system=row.source_system,
                evidence=NormalizedBankEvidence(
                    **row.model_dump(exclude={"source_system"})
                ),
            )
            if disposition.disposition == "replay":
                replayed += 1
            else:
                persisted += 1
            dispositions.append(disposition)
        return BankImportConfirmResponse(
            preview_digest=preview.preview_digest,
            persisted_count=persisted,
            replay_count=replayed,
            quarantined_count=quarantined,
            dispositions=tuple(dispositions),
        )

    async def review_queue(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        account_id: UUID | None = None,
    ) -> tuple[BankMatchReviewItem, ...]:
        statement = (
            select(BankTransaction, BankTransactionMatch)
            .outerjoin(
                BankTransactionMatch,
                (BankTransactionMatch.company_id == BankTransaction.company_id)
                & (BankTransactionMatch.bank_transaction_id == BankTransaction.id),
            )
            .where(BankTransaction.company_id == company_id)
        )
        if account_id is not None:
            statement = statement.where(BankTransaction.bank_account_id == account_id)
        rows = tuple((await session.execute(statement)).all())
        return tuple(
            BankMatchReviewItem(
                transaction=BankTransactionResponse.model_validate(transaction),
                match_id=match.id if match else None,
                match_state=(
                    match.state
                    if match
                    else (
                        "review_required"
                        if transaction.state == "pending"
                        else "unmatched"
                    )
                ),
                target_type=match.target_type if match else None,
                target_identity=match.target_identity if match else None,
                reason_code=(
                    match.reason_code
                    if match
                    else (
                        "PENDING_SOURCE"
                        if transaction.state == "pending"
                        else "NO_DECISION"
                    )
                ),
                deterministic=match.deterministic if match else False,
            )
            for transaction, match in rows
        )

    async def reconciliation_preview(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        account_id: UUID,
        request: BankReconciliationPreviewRequest,
    ) -> BankReconciliationPreviewResponse:
        account = await self._account(session, company_id, account_id)
        prior = await session.scalar(
            select(BankReconciliation)
            .where(
                BankReconciliation.company_id == company_id,
                BankReconciliation.bank_account_id == account_id,
                BankReconciliation.status == "closed",
                BankReconciliation.period_end < request.period_start,
            )
            .order_by(BankReconciliation.period_end.desc())
            .limit(1)
        )
        beginning = (
            prior.ending_balance if prior else (account.opening_balance or Decimal(0))
        )
        selected = tuple(
            (
                await session.scalars(
                    select(BankTransaction).where(
                        BankTransaction.company_id == company_id,
                        BankTransaction.bank_account_id == account_id,
                        BankTransaction.id.in_(request.cleared_transaction_ids),
                        BankTransaction.state == "posted",
                        BankTransaction.posted_date.between(
                            request.period_start, request.period_end
                        ),
                    )
                )
            ).all()
        )
        cleared = sum(
            (_signed(row.direction, row.amount) for row in selected), Decimal(0)
        )
        if account.ledger_account_id is None:
            raise AccountingValidation("Approved GL mapping is required")
        book = await self._book_cash_balance(
            session, company_id, account.ledger_account_id, request.period_end
        )
        outstanding = book - beginning - cleared
        difference = request.ending_balance - book
        blockers: list[str] = []
        if len(selected) != len(set(request.cleared_transaction_ids)):
            blockers.append("CLEARED_TRANSACTION_SCOPE_MISMATCH")
        unresolved = sum(
            1
            for row in await self.review_queue(
                session, company_id=company_id, account_id=account_id
            )
            if row.match_state in {"ambiguous", "review_required"}
        )
        if unresolved:
            blockers.append("UNRESOLVED_MATCH_REVIEW")
        if difference != 0:
            blockers.append("NON_ZERO_DIFFERENCE")
        return BankReconciliationPreviewResponse(
            bank_account_id=account_id,
            statement_identity=request.statement_identity,
            period_start=request.period_start,
            period_end=request.period_end,
            beginning_balance=beginning,
            ending_balance=request.ending_balance,
            book_balance=book,
            cleared_total=cleared,
            outstanding_total=outstanding,
            difference=difference,
            unresolved_exceptions=unresolved,
            can_close=not blockers,
            blocker_reasons=tuple(blockers),
        )

    async def _book_cash_balance(
        self,
        session: AsyncSession,
        company_id: UUID,
        ledger_account_id: UUID,
        cutoff: date,
    ) -> Decimal:
        value = await session.scalar(
            select(func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0))
            .join(Journal, Journal.id == JournalLine.journal_id)
            .where(
                Journal.company_id == company_id,
                Journal.status == "posted",
                Journal.effective_date <= cutoff,
                JournalLine.company_id == company_id,
                JournalLine.account_id == ledger_account_id,
            )
        )
        return Decimal(value or 0)

    async def history(
        self, session: AsyncSession, *, company_id: UUID, account_id: UUID
    ) -> tuple[BankReconciliationResponse, ...]:
        await self._account(session, company_id, account_id)
        rows = await session.scalars(
            select(BankReconciliation)
            .where(
                BankReconciliation.company_id == company_id,
                BankReconciliation.bank_account_id == account_id,
                BankReconciliation.status == "closed",
            )
            .order_by(BankReconciliation.period_end.desc())
        )
        return tuple(
            [await self.reconciliation_response(session, row) for row in rows.all()]
        )

    async def reconciliations(
        self, session: AsyncSession, *, company_id: UUID, account_id: UUID
    ) -> tuple[BankReconciliationResponse, ...]:
        await self._account(session, company_id, account_id)
        rows = await session.scalars(
            select(BankReconciliation)
            .where(
                BankReconciliation.company_id == company_id,
                BankReconciliation.bank_account_id == account_id,
            )
            .order_by(BankReconciliation.prepared_at.desc())
        )
        return tuple(
            [await self.reconciliation_response(session, row) for row in rows.all()]
        )

    async def drilldown(
        self, session: AsyncSession, *, company_id: UUID, transaction_id: UUID
    ) -> BankDrilldownResponse:
        row = (
            await session.execute(
                select(BankTransaction, BankTransactionMatch, BankAccount)
                .join(BankAccount, BankAccount.id == BankTransaction.bank_account_id)
                .outerjoin(
                    BankTransactionMatch,
                    BankTransactionMatch.bank_transaction_id == BankTransaction.id,
                )
                .where(
                    BankTransaction.company_id == company_id,
                    BankAccount.company_id == company_id,
                    BankTransaction.id == transaction_id,
                )
            )
        ).one_or_none()
        if row is None:
            raise AccountingNotFound("Bank transaction was not found")
        transaction, match, account = row
        review = await self.review_queue(
            session, company_id=company_id, account_id=account.id
        )
        item = next(value for value in review if value.transaction.id == transaction.id)
        return BankDrilldownResponse(
            transaction=BankTransactionResponse.model_validate(transaction),
            match=item,
            bank_account_id=account.id,
            ledger_account_id=account.ledger_account_id,
            target_reference=match.target_identity if match else None,
            source_system=transaction.source_system,
            source_digest=transaction.source_digest,
        )

    async def cash_flow(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        period_start: date,
        period_end: date,
        basis: str,
    ) -> CashFlowResponse:
        if basis != "posted_cash_movement":
            raise AccountingConflict(
                "Cash Flow supports only canonical posted cash-movement evidence"
            )
        accounts = tuple(
            (
                await session.scalars(
                    select(BankAccount).where(
                        BankAccount.company_id == company_id,
                        BankAccount.status == "active",
                    )
                )
            ).all()
        )
        ledger_ids = tuple(row.ledger_account_id for row in accounts)
        rows = (
            tuple(
                (
                    await session.execute(
                        select(Journal, JournalLine)
                        .join(JournalLine, JournalLine.journal_id == Journal.id)
                        .where(
                            Journal.company_id == company_id,
                            Journal.status == "posted",
                            Journal.effective_date.between(period_start, period_end),
                            JournalLine.company_id == company_id,
                            JournalLine.account_id.in_(ledger_ids),
                        )
                    )
                ).all()
            )
            if ledger_ids
            else ()
        )
        sections: dict[str, list[tuple[UUID, Decimal]]] = {
            "operating": [],
            "investing": [],
            "financing": [],
            "unclassified": [],
        }
        operating = {
            "customer_payment",
            "payment_deposit",
            "merchant_settlement",
            "merchant_fee",
            "vendor_payment",
            "payroll_payment",
            "payroll_liability_payment",
            "payroll_tax_payment",
        }
        investing = {"asset_purchase", "capital_expenditure", "asset_sale"}
        financing = {
            "owner_contribution",
            "owner_distribution",
            "loan_proceeds",
            "loan_payment",
        }
        for journal, line in rows:
            amount = line.debit - line.credit
            if journal.source_type == "bank_transfer":
                continue
            section_name = (
                "operating"
                if journal.source_type in operating
                else "investing"
                if journal.source_type in investing
                else "financing"
                if journal.source_type in financing
                else "unclassified"
            )
            sections[section_name].append((journal.id, amount))
        beginning = Decimal(0)
        for account in accounts:
            if account.ledger_account_id is None:
                continue
            beginning += await self._book_cash_balance(
                session,
                company_id,
                account.ledger_account_id,
                date.fromordinal(period_start.toordinal() - 1),
            )

        def build_section(name: str) -> CashFlowSection:
            return CashFlowSection(
                amount=sum((value for _, value in sections[name]), Decimal(0)),
                journal_ids=tuple(identity for identity, _ in sections[name]),
            )

        op = build_section("operating")
        inv = build_section("investing")
        fin = build_section("financing")
        unclassified = sum((value for _, value in sections["unclassified"]), Decimal(0))
        net = op.amount + inv.amount + fin.amount + unclassified
        ending = beginning + net
        reconciliations = (
            tuple(
                (
                    await session.scalars(
                        select(BankReconciliation).where(
                            BankReconciliation.company_id == company_id,
                            BankReconciliation.bank_account_id.in_(
                                tuple(a.id for a in accounts)
                            ),
                            BankReconciliation.period_end == period_end,
                            BankReconciliation.status == "closed",
                        )
                    )
                ).all()
            )
            if accounts
            else ()
        )
        canonical = (
            sum((row.ending_balance for row in reconciliations), Decimal(0))
            if len(reconciliations) == len(accounts) and accounts
            else None
        )
        difference = ending - canonical if canonical is not None else None
        completeness = (
            "UNAVAILABLE"
            if not accounts
            else "COMPLETE"
            if not sections["unclassified"] and canonical is not None
            else "PARTIAL"
        )
        return CashFlowResponse(
            period_start=period_start,
            period_end=period_end,
            basis=basis,
            cutoff=period_end,
            completeness=completeness,
            beginning_cash=beginning,
            operating_activities=op,
            investing_activities=inv,
            financing_activities=fin,
            unclassified_amount=unclassified,
            unclassified_journal_ids=tuple(i for i, _ in sections["unclassified"]),
            net_change=net,
            ending_cash=ending,
            canonical_bank_cash=canonical,
            difference=difference,
            tie_status=(
                "TIED"
                if difference == 0
                else "REVIEW_REQUIRED"
                if difference is not None
                else "UNAVAILABLE"
            ),
        )


banking_operator_service = BankingOperatorService()
