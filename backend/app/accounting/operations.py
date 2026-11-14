"""Current-accounting operational registers backed by the canonical ledger."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingValidation,
)
from app.accounting.models import (
    Account,
    AccountingOperation,
    AccountingPeriod,
    Journal,
)
from app.accounting.repository import accounting_repository
from app.accounting.schemas import AccountingOperationCreate
from app.accounting.service import accounting_service
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.permissions.authorization import AuthorizationContext

OPERATION_KINDS = {
    "undeposited_receipt",
    "deposit",
    "card_account",
    "card_charge",
    "card_credit",
    "card_payment",
    "fixed_asset",
    "depreciation",
    "tax_accrual",
    "tax_payment",
    "inventory_valuation",
    "inventory_purchase",
    "inventory_usage",
    "inventory_adjustment",
    "job_cost",
    "cutover_activation",
}
REGISTER_ONLY_KINDS = {"card_account", "cutover_activation"}
RELATED_KINDS = {
    "card_charge": "card_account",
    "card_credit": "card_account",
    "card_payment": "card_account",
    "depreciation": "fixed_asset",
}


class AccountingOperationService:
    @staticmethod
    def _validate(data: AccountingOperationCreate) -> None:
        if data.kind not in OPERATION_KINDS:
            raise AccountingValidation("Accounting operation kind is invalid")
        if not data.provenance.get("source") or not data.provenance.get(
            "evidence_reference"
        ):
            raise AccountingValidation(
                "Operation provenance requires source and evidence_reference"
            )
        if data.kind in REGISTER_ONLY_KINDS:
            if data.amount != 0 or data.journal is not None:
                raise AccountingValidation("Register-only operations cannot post money")
        elif data.amount <= 0 or data.journal is None:
            raise AccountingValidation(
                "Financial operations require a positive journal"
            )
        if data.journal is not None:
            if data.journal.effective_date != data.effective_date:
                raise AccountingValidation("Operation and journal dates must match")
            if data.journal.currency != data.currency:
                raise AccountingValidation(
                    "Operation and journal currencies must match"
                )
            if data.journal.source_type != data.kind:
                raise AccountingValidation(
                    "Journal source type must match operation kind"
                )
            if data.journal.source_identity != data.reference:
                raise AccountingValidation(
                    "Journal source identity must match operation reference"
                )
            total = sum((line.debit for line in data.journal.lines), Decimal(0))
            if total != data.amount:
                raise AccountingValidation("Operation amount must equal journal debits")
        required_payload = {
            "undeposited_receipt": ("payment_reference", "customer_reference"),
            "deposit": ("payment_references", "bank_account_reference"),
            "card_account": ("masked_identity", "account_name"),
            "fixed_asset": (
                "placed_in_service_date",
                "useful_life_months",
                "depreciation_method",
            ),
            "depreciation": ("depreciation_period",),
            "tax_accrual": ("tax_type", "liability_period"),
            "tax_payment": ("tax_type", "payment_reference"),
            "inventory_valuation": ("valuation_method",),
            "inventory_purchase": ("inventory_item_id", "quantity"),
            "inventory_usage": ("inventory_item_id", "quantity", "job_id"),
            "inventory_adjustment": ("inventory_item_id", "reason"),
            "job_cost": ("job_id", "cost_category"),
            "cutover_activation": (
                "accepted_capabilities",
                "acceptance_evidence_reference",
            ),
        }
        missing = [
            field
            for field in required_payload.get(data.kind, ())
            if data.payload.get(field) in (None, "", [])
        ]
        if missing:
            raise AccountingValidation(
                "Operation payload is missing: " + ", ".join(missing)
            )

    async def create(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: AccountingOperationCreate,
    ) -> AccountingOperation:
        self._validate(data)
        try:
            async with session.begin():
                existing = await session.scalar(
                    select(AccountingOperation).where(
                        AccountingOperation.company_id == context.company.id,
                        AccountingOperation.kind == data.kind,
                        AccountingOperation.reference == data.reference.strip(),
                    )
                )
                if existing is not None:
                    if (
                        existing.amount != data.amount
                        or existing.provenance != data.provenance
                        or existing.payload != data.payload
                    ):
                        raise AccountingConflict(
                            "Operation reference conflicts with existing evidence"
                        )
                    return existing
                if data.kind == "deposit":
                    payment_references = {
                        str(value).strip()
                        for value in data.payload["payment_references"]
                        if str(value).strip()
                    }
                    for payment_reference in sorted(payment_references):
                        await session.execute(
                            text(
                                "SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"
                            ),
                            {
                                "identity": (
                                    f"accounting-deposit:{context.company.id}:"
                                    f"{payment_reference}"
                                )
                            },
                        )
                    prior_deposits = (
                        await session.scalars(
                            select(AccountingOperation).where(
                                AccountingOperation.company_id == context.company.id,
                                AccountingOperation.kind == "deposit",
                            )
                        )
                    ).all()
                    receipt_references = set(
                        await session.scalars(
                            select(AccountingOperation.reference).where(
                                AccountingOperation.company_id == context.company.id,
                                AccountingOperation.kind == "undeposited_receipt",
                                AccountingOperation.reference.in_(payment_references),
                            )
                        )
                    )
                    if receipt_references != payment_references:
                        raise AccountingValidation(
                            "Every deposit payment requires an Undeposited Funds receipt"
                        )
                    if any(
                        payment_references
                        & {
                            str(value).strip()
                            for value in prior.payload.get("payment_references", [])
                        }
                        for prior in prior_deposits
                    ):
                        raise AccountingConflict(
                            "A payment is already assigned to another deposit"
                        )
                related = None
                if data.related_operation_id is not None:
                    related = await session.scalar(
                        select(AccountingOperation).where(
                            AccountingOperation.company_id == context.company.id,
                            AccountingOperation.id == data.related_operation_id,
                        )
                    )
                    if related is None:
                        raise AccountingNotFound(
                            "Related accounting operation was not found"
                        )
                expected = RELATED_KINDS.get(data.kind)
                if expected and (related is None or related.kind != expected):
                    raise AccountingValidation(
                        f"{data.kind} requires a related {expected} register item"
                    )
                journal = None
                if data.journal is not None:
                    journal = await accounting_service.create_journal(
                        session,
                        context=context,
                        data=data.journal,
                        allow_control_override=False,
                        manage_transaction=False,
                    )
                row = AccountingOperation(
                    company_id=context.company.id,
                    kind=data.kind,
                    reference=data.reference.strip(),
                    status="active" if journal is None else journal.status,
                    effective_date=data.effective_date,
                    amount=data.amount,
                    currency=data.currency,
                    journal_id=journal.id if journal else None,
                    related_operation_id=related.id if related else None,
                    payload=data.payload,
                    provenance=data.provenance,
                    created_by_user_id=context.user.id,
                )
                session.add(row)
                await session.flush()
                AuditService.stage(
                    session,
                    AuditEntry(
                        action="accounting.operation.created",
                        resource_type="accounting_operation",
                        actor_user_id=context.user.id,
                        company_id=context.company.id,
                        resource_id=row.id,
                        details={"kind": row.kind, "reference": row.reference},
                    ),
                )
                return row
        except IntegrityError as error:
            raise AccountingConflict("Accounting operation already exists") from error

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        kind: str | None = None,
    ) -> tuple[tuple[AccountingOperation, str | None], ...]:
        query = (
            select(AccountingOperation, Journal.status)
            .outerjoin(
                Journal,
                (Journal.company_id == AccountingOperation.company_id)
                & (Journal.id == AccountingOperation.journal_id),
            )
            .where(AccountingOperation.company_id == context.company.id)
            .order_by(
                AccountingOperation.effective_date.desc(),
                AccountingOperation.created_at.desc(),
            )
        )
        if kind:
            if kind not in OPERATION_KINDS:
                raise AccountingValidation("Accounting operation kind is invalid")
            query = query.where(AccountingOperation.kind == kind)
        rows = tuple(
            (row, status) for row, status in (await session.execute(query)).all()
        )
        posted = {
            row.id: (row, status)
            for row, status in rows
            if status == "posted" or row.journal_id is None
        }
        for row, _status in rows:
            enriched = dict(row.payload)
            if row.kind == "card_account":
                liability = sum(
                    (
                        item.amount if item.kind == "card_charge" else -item.amount
                        for item, _ in posted.values()
                        if item.related_operation_id == row.id
                        and item.kind in {"card_charge", "card_credit", "card_payment"}
                    ),
                    Decimal(0),
                )
                enriched["liability_balance"] = str(liability)
            elif row.kind == "fixed_asset":
                accumulated = sum(
                    (
                        item.amount
                        for item, _ in posted.values()
                        if item.related_operation_id == row.id
                        and item.kind == "depreciation"
                    ),
                    Decimal(0),
                )
                enriched["basis"] = str(row.amount)
                enriched["accumulated_depreciation"] = str(accumulated)
                enriched["carrying_value"] = str(row.amount - accumulated)
            elif row.kind in {"tax_accrual", "tax_payment"}:
                tax_type = row.payload.get("tax_type")
                remaining = sum(
                    (
                        item.amount if item.kind == "tax_accrual" else -item.amount
                        for item, _ in posted.values()
                        if item.kind in {"tax_accrual", "tax_payment"}
                        and item.payload.get("tax_type") == tax_type
                    ),
                    Decimal(0),
                )
                enriched["remaining_liability"] = str(remaining)
            row.payload = enriched
        return rows

    async def dashboard(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> dict[str, object]:
        company_id = context.company.id
        account_count = await session.scalar(
            select(func.count(Account.id)).where(Account.company_id == company_id)
        )
        active_count = await session.scalar(
            select(func.count(Account.id)).where(
                Account.company_id == company_id, Account.status == "active"
            )
        )
        open_period_count = await session.scalar(
            select(func.count(AccountingPeriod.id)).where(
                AccountingPeriod.company_id == company_id,
                AccountingPeriod.status.in_(("open", "reopened")),
            )
        )
        operation_rows = (
            await session.execute(
                select(AccountingOperation.kind, func.count(AccountingOperation.id))
                .where(AccountingOperation.company_id == company_id)
                .group_by(AccountingOperation.kind)
            )
        ).all()
        discrepancy_count = await session.scalar(
            select(func.count(AccountingOperation.id)).where(
                AccountingOperation.company_id == company_id,
                AccountingOperation.provenance["classification"].astext.in_(
                    ("DISCREPANCY", "QUARANTINED", "PROVISIONAL")
                ),
            )
        )
        debits, credits = await accounting_repository.trial_balance(session, company_id)
        return {
            "account_count": account_count or 0,
            "active_account_count": active_count or 0,
            "open_period_count": open_period_count or 0,
            "close_status": "OPEN" if open_period_count else "NO_OPEN_PERIOD",
            "discrepancy_count": discrepancy_count or 0,
            "operation_counts": {kind: count for kind, count in operation_rows},
            "trial_balance_debits": debits,
            "trial_balance_credits": credits,
            "balanced": debits == credits,
        }


accounting_operation_service = AccountingOperationService()
