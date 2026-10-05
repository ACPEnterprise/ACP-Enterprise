"""Provider-neutral, read-only bank connectivity and Accounting evidence handoff."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
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
    BankAccountGLMapping,
    BankBalanceEvidence,
    BankConnection,
    BankReconciliation,
    BankTransaction,
    BankTransactionEvidenceVersion,
    BankTransactionMatch,
)
from app.platform.permissions.authorization import AuthorizationContext


class BankingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ConnectionCreate(BankingModel):
    provider: str
    provider_institution_id: str
    provider_connection_id: str
    institution_name: str
    credential_reference: str
    branch_id: UUID | None = None
    provider_version: str | None = None
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConnectionView(BankingModel):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    provider: str
    provider_institution_id: str
    institution_name: str
    consent_status: str
    status: str
    provider_version: str | None
    source_as_of: datetime | None
    last_successful_sync_at: datetime | None
    last_error_code: str | None
    account_count: int = 0


class ProviderAccount(BankingModel):
    provider_account_id: str
    name: str
    official_name: str | None = None
    account_type: str
    subtype: str | None = None
    mask: str | None = None
    currency: str
    current_balance: Decimal | None
    available_balance: Decimal | None
    balance_as_of: datetime
    provider_metadata: dict[str, object] = Field(default_factory=dict)


class ProviderTransaction(BankingModel):
    provider_transaction_id: str
    provider_account_id: str
    pending_transaction_id: str | None = None
    pending: bool
    transaction_date: date
    authorized_date: date | None = None
    amount: Decimal
    currency: str
    name: str
    merchant_name: str | None = None
    provider_metadata: dict[str, object] = Field(default_factory=dict)
    category_metadata: dict[str, object] = Field(default_factory=dict)


class RemovedTransaction(BankingModel):
    provider_transaction_id: str


class ProviderSyncPage(BankingModel):
    added: tuple[ProviderTransaction, ...] = ()
    modified: tuple[ProviderTransaction, ...] = ()
    removed: tuple[RemovedTransaction, ...] = ()
    next_cursor: str
    has_more: bool
    request_id: str | None = None
    source_as_of: datetime


class SyncResult(BankingModel):
    connection_id: UUID
    added: int
    modified: int
    removed: int
    replayed: int
    cursor: str
    evidence_digest: str


class GLMappingRequest(BankingModel):
    ledger_account_id: UUID
    expected_account_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class GLMappingView(BankingModel):
    id: UUID
    bank_account_id: UUID
    ledger_account_id: UUID
    status: str
    version: int
    evidence_digest: str
    approved_at: datetime


class BankAccountingEvidence(BankingModel):
    bank_account_id: UUID
    display_identity: str
    provider: str
    connection_status: str
    mapped_ledger_account_id: UUID | None
    mapping_state: str
    bank_current_balance: Decimal | None
    bank_available_balance: Decimal | None
    bank_balance_as_of: datetime | None
    book_balance: Decimal | None
    cutoff: date
    unresolved_transaction_count: int
    reconciliation_status: str
    reconciliation_difference: Decimal | None
    readiness: str
    blockers: tuple[str, ...]
    provenance: tuple[str, ...]
    evidence_digest: str


class ProtectedCredentialResolver(Protocol):
    async def resolve(self, credential_reference: str) -> str: ...


class ProviderTransport(Protocol):
    async def post(
        self, path: str, payload: dict[str, object], *, access_token: str
    ) -> dict[str, object]: ...


class BankProviderAdapter(Protocol):
    provider: str

    async def accounts(self, access_token: str) -> tuple[ProviderAccount, ...]: ...
    async def transaction_page(
        self, access_token: str, cursor: str | None
    ) -> ProviderSyncPage: ...


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class PlaidReadOnlyAdapter:
    """Plaid adapter using Accounts/Balance and cursor-based Transactions Sync."""

    provider = "plaid"

    def __init__(self, transport: ProviderTransport) -> None:
        self.transport = transport

    async def accounts(self, access_token: str) -> tuple[ProviderAccount, ...]:
        data = await self.transport.post(
            "/accounts/balance/get", {}, access_token=access_token
        )
        now = datetime.now(timezone.utc)
        return tuple(
            ProviderAccount(
                provider_account_id=str(item["account_id"]),
                name=str(item.get("name") or "Bank account"),
                official_name=str(item["official_name"])
                if item.get("official_name")
                else None,
                account_type=str(item.get("type") or "other"),
                subtype=str(item["subtype"]) if item.get("subtype") else None,
                mask=str(item["mask"]) if item.get("mask") else None,
                currency=str(
                    (item.get("balances") or {}).get("iso_currency_code") or "USD"
                ),
                current_balance=_decimal((item.get("balances") or {}).get("current")),
                available_balance=_decimal(
                    (item.get("balances") or {}).get("available")
                ),
                balance_as_of=now,
                provider_metadata={
                    "persistent_account_id": item.get("persistent_account_id")
                },
            )
            for item in cast(list[object], data.get("accounts", []))
            if isinstance(item, dict)
        )

    async def transaction_page(
        self, access_token: str, cursor: str | None
    ) -> ProviderSyncPage:
        payload: dict[str, object] = {"count": 500}
        if cursor:
            payload["cursor"] = cursor
        data = await self.transport.post(
            "/transactions/sync", payload, access_token=access_token
        )
        now = datetime.now(timezone.utc)
        return ProviderSyncPage(
            added=tuple(
                _plaid_transaction(item)
                for item in cast(list[object], data.get("added", []))
                if isinstance(item, dict)
            ),
            modified=tuple(
                _plaid_transaction(item)
                for item in cast(list[object], data.get("modified", []))
                if isinstance(item, dict)
            ),
            removed=tuple(
                RemovedTransaction(provider_transaction_id=str(item["transaction_id"]))
                for item in cast(list[object], data.get("removed", []))
                if isinstance(item, dict)
            ),
            next_cursor=str(data["next_cursor"]),
            has_more=bool(data.get("has_more")),
            request_id=str(data["request_id"]) if data.get("request_id") else None,
            source_as_of=now,
        )


def _decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _plaid_transaction(item: dict[str, object]) -> ProviderTransaction:
    currency = str(
        item.get("iso_currency_code") or item.get("unofficial_currency_code") or "USD"
    )
    return ProviderTransaction(
        provider_transaction_id=str(item["transaction_id"]),
        provider_account_id=str(item["account_id"]),
        pending_transaction_id=str(item["pending_transaction_id"])
        if item.get("pending_transaction_id")
        else None,
        pending=bool(item.get("pending")),
        transaction_date=date.fromisoformat(str(item["date"])),
        authorized_date=date.fromisoformat(str(item["authorized_date"]))
        if item.get("authorized_date")
        else None,
        amount=Decimal(str(item["amount"])),
        currency=currency,
        name=str(item.get("name") or "Bank transaction"),
        merchant_name=str(item["merchant_name"]) if item.get("merchant_name") else None,
        provider_metadata={
            "payment_channel": item.get("payment_channel"),
            "merchant_entity_id": item.get("merchant_entity_id"),
        },
        category_metadata={
            "personal_finance_category": item.get("personal_finance_category"),
            "merchant_category_code": item.get("merchant_category_code"),
        },
    )


class BankConnectivityService:
    async def create_connection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: ConnectionCreate,
    ) -> BankConnection:
        if request.branch_id is not None and not context.can_access_branch(
            request.branch_id
        ):
            raise AccountingNotFound("Bank connection Branch was not found")
        if not request.credential_reference.startswith("secret://"):
            raise AccountingValidation("Protected credential reference is required")
        row = BankConnection(
            company_id=context.company.id,
            branch_id=request.branch_id,
            provider=request.provider,
            provider_institution_id=request.provider_institution_id,
            provider_connection_id=request.provider_connection_id,
            institution_name=request.institution_name,
            credential_reference=request.credential_reference,
            consent_status="active",
            status="pending",
            provider_version=request.provider_version,
            source_digest=request.source_digest,
            created_by_user_id=context.user.id,
        )
        session.add(row)
        await session.flush()
        return row

    async def synchronize(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        connection_id: UUID,
        adapter: BankProviderAdapter,
        resolver: ProtectedCredentialResolver,
    ) -> SyncResult:
        connection = await session.scalar(
            select(BankConnection)
            .where(
                BankConnection.company_id == context.company.id,
                BankConnection.id == connection_id,
            )
            .with_for_update()
        )
        if connection is None:
            raise AccountingNotFound("Bank connection was not found")
        if connection.branch_id is not None and not context.can_access_branch(
            connection.branch_id
        ):
            raise AccountingNotFound("Bank connection was not found")
        if adapter.provider != connection.provider:
            raise AccountingConflict("Bank provider adapter does not match connection")
        token = await resolver.resolve(connection.credential_reference)
        accounts = await adapter.accounts(token)
        by_provider: dict[str, BankAccount] = {}
        for item in accounts:
            digest = _digest(item.model_dump(mode="json"))
            account = await session.scalar(
                select(BankAccount).where(
                    BankAccount.company_id == context.company.id,
                    BankAccount.source_system == connection.provider,
                    BankAccount.source_account_id == item.provider_account_id,
                )
            )
            if account is None:
                account = BankAccount(
                    company_id=context.company.id,
                    connection_id=connection.id,
                    branch_id=connection.branch_id,
                    ledger_account_id=None,
                    institution_name=connection.institution_name,
                    account_name=item.official_name or item.name,
                    account_type=_account_type(item.account_type, item.subtype),
                    account_subtype=item.subtype,
                    ownership_scope="branch" if connection.branch_id else "company",
                    masked_identity=f"••••{item.mask}" if item.mask else "Not provided",
                    currency=item.currency,
                    status="active",
                    source_system=connection.provider,
                    source_account_id=item.provider_account_id,
                    source_version=connection.provider_version or "provider-current",
                    source_digest=digest,
                    source_as_of=item.balance_as_of,
                    created_by_user_id=context.user.id,
                )
                session.add(account)
                await session.flush()
            else:
                account.source_digest, account.source_as_of, account.updated_at = (
                    digest,
                    item.balance_as_of,
                    datetime.now(timezone.utc),
                )
            by_provider[item.provider_account_id] = account
            balance_digest = _digest(
                [
                    digest,
                    item.current_balance,
                    item.available_balance,
                    item.balance_as_of,
                ]
            )
            exists = await session.scalar(
                select(BankBalanceEvidence.id).where(
                    BankBalanceEvidence.company_id == context.company.id,
                    BankBalanceEvidence.bank_account_id == account.id,
                    BankBalanceEvidence.source_digest == balance_digest,
                )
            )
            if exists is None:
                session.add(
                    BankBalanceEvidence(
                        company_id=context.company.id,
                        bank_account_id=account.id,
                        current_balance=item.current_balance,
                        available_balance=item.available_balance,
                        currency=item.currency,
                        balance_as_of=item.balance_as_of,
                        acquired_at=datetime.now(timezone.utc),
                        provider_cursor=connection.cursor,
                        source_digest=balance_digest,
                        provenance={
                            "provider": connection.provider,
                            "connection_id": str(connection.id),
                        },
                    )
                )
        added = modified = removed = replayed = 0
        cursor = connection.cursor
        while True:
            page = await adapter.transaction_page(token, cursor)
            for change_type, values in (
                ("added", page.added),
                ("modified", page.modified),
            ):
                for value in values:
                    account = by_provider.get(value.provider_account_id)
                    if account is None:
                        raise AccountingConflict(
                            "Provider transaction references an unavailable account"
                        )
                    changed = await self._upsert_transaction(
                        session,
                        context.company.id,
                        account,
                        connection.provider,
                        value,
                        page.next_cursor,
                        change_type,
                    )
                    if changed == "replay":
                        replayed += 1
                    elif change_type == "added":
                        added += 1
                    else:
                        modified += 1
            for removed_value in page.removed:
                row = await session.scalar(
                    select(BankTransaction).where(
                        BankTransaction.company_id == context.company.id,
                        BankTransaction.source_system == connection.provider,
                        BankTransaction.external_transaction_id
                        == removed_value.provider_transaction_id,
                    )
                )
                if row and row.evidence_status != "removed":
                    row.evidence_status = "removed"
                    digest = _digest(
                        [
                            removed_value.provider_transaction_id,
                            page.next_cursor,
                            "removed",
                        ]
                    )
                    session.add(
                        BankTransactionEvidenceVersion(
                            company_id=context.company.id,
                            bank_transaction_id=row.id,
                            provider_transaction_id=removed_value.provider_transaction_id,
                            provider_cursor=page.next_cursor,
                            change_type="removed",
                            source_digest=digest,
                            evidence=removed_value.model_dump(mode="json"),
                            acquired_at=datetime.now(timezone.utc),
                        )
                    )
                    removed += 1
            cursor = page.next_cursor
            if not page.has_more:
                break
        connection.cursor, connection.status = cursor, "healthy"
        connection.last_successful_sync_at = connection.source_as_of = datetime.now(
            timezone.utc
        )
        connection.last_error_code = None
        return SyncResult(
            connection_id=connection.id,
            added=added,
            modified=modified,
            removed=removed,
            replayed=replayed,
            cursor=cursor or "",
            evidence_digest=_digest([connection.id, cursor, added, modified, removed]),
        )

    async def _upsert_transaction(
        self,
        session: AsyncSession,
        company_id: UUID,
        account: BankAccount,
        provider: str,
        value: ProviderTransaction,
        cursor: str,
        change_type: str,
    ) -> str:
        evidence = value.model_dump(mode="json")
        digest = _digest(evidence)
        row = await session.scalar(
            select(BankTransaction)
            .where(
                BankTransaction.company_id == company_id,
                BankTransaction.bank_account_id == account.id,
                BankTransaction.source_system == provider,
                BankTransaction.external_transaction_id
                == value.provider_transaction_id,
            )
            .with_for_update()
        )
        if row and row.source_digest == digest:
            return "replay"
        if row is None:
            amount = abs(value.amount)
            pending = None
            if value.pending_transaction_id:
                pending = await session.scalar(
                    select(BankTransaction)
                    .where(
                        BankTransaction.company_id == company_id,
                        BankTransaction.bank_account_id == account.id,
                        BankTransaction.source_system == provider,
                        BankTransaction.external_transaction_id
                        == value.pending_transaction_id,
                    )
                    .with_for_update()
                )
                if pending:
                    pending.evidence_status = "superseded"
            row = BankTransaction(
                company_id=company_id,
                bank_account_id=account.id,
                source_system=provider,
                external_transaction_id=value.provider_transaction_id,
                related_identity=value.pending_transaction_id,
                group_key=None,
                source_version=cursor,
                source_digest=digest,
                acquired_at=datetime.now(timezone.utc),
                source_as_of=datetime.now(timezone.utc),
                posted_date=value.transaction_date,
                effective_date=value.transaction_date,
                authorized_date=value.authorized_date,
                pending_transaction_id=value.pending_transaction_id,
                amount=amount,
                currency=value.currency,
                direction="outflow" if value.amount >= 0 else "inflow",
                kind="other",
                description=value.merchant_name or value.name,
                memo=None,
                state="pending" if value.pending else "posted",
                evidence_status="active",
                provider_metadata=value.provider_metadata,
                category_metadata=value.category_metadata,
                provider_cursor=cursor,
            )
            session.add(row)
            await session.flush()
        else:
            row.prior_source_digest, row.source_digest, row.source_version = (
                row.source_digest,
                digest,
                cursor,
            )
            row.pending_transaction_id, row.state = (
                value.pending_transaction_id,
                "pending" if value.pending else "posted",
            )
            row.posted_date, row.authorized_date, row.amount = (
                value.transaction_date,
                value.authorized_date,
                abs(value.amount),
            )
            row.direction, row.description = (
                ("outflow" if value.amount >= 0 else "inflow"),
                value.merchant_name or value.name,
            )
            row.provider_metadata, row.category_metadata, row.provider_cursor = (
                value.provider_metadata,
                value.category_metadata,
                cursor,
            )
        session.add(
            BankTransactionEvidenceVersion(
                company_id=company_id,
                bank_transaction_id=row.id,
                provider_transaction_id=value.provider_transaction_id,
                provider_cursor=cursor,
                change_type=change_type,
                source_digest=digest,
                evidence=evidence,
                acquired_at=datetime.now(timezone.utc),
            )
        )
        return "changed"

    async def approve_mapping(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bank_account_id: UUID,
        request: GLMappingRequest,
    ) -> BankAccountGLMapping:
        account = await session.scalar(
            select(BankAccount)
            .where(
                BankAccount.company_id == context.company.id,
                BankAccount.id == bank_account_id,
            )
            .with_for_update()
        )
        ledger = await session.scalar(
            select(Account).where(
                Account.company_id == context.company.id,
                Account.id == request.ledger_account_id,
            )
        )
        if account is None or ledger is None:
            raise AccountingNotFound("Bank or ledger account was not found")
        if account.branch_id is not None and not context.can_access_branch(
            account.branch_id
        ):
            raise AccountingNotFound("Bank or ledger account was not found")
        if account.source_digest != request.expected_account_source_digest:
            raise AccountingConflict(
                "Bank account evidence changed before mapping approval"
            )
        prior = await session.scalar(
            select(BankAccountGLMapping)
            .where(
                BankAccountGLMapping.company_id == context.company.id,
                BankAccountGLMapping.bank_account_id == account.id,
                BankAccountGLMapping.status == "approved",
            )
            .with_for_update()
        )
        version = 1
        if prior:
            prior.status, prior.superseded_at = "superseded", datetime.now(timezone.utc)
            version = prior.version + 1
        digest = _digest([account.id, ledger.id, version, account.source_digest])
        row = BankAccountGLMapping(
            company_id=context.company.id,
            bank_account_id=account.id,
            ledger_account_id=ledger.id,
            status="approved",
            version=version,
            evidence_digest=digest,
            approved_by_user_id=context.user.id,
        )
        account.ledger_account_id = ledger.id
        session.add(row)
        await session.flush()
        return row

    async def accounting_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        bank_account_id: UUID,
        cutoff: date,
    ) -> BankAccountingEvidence:
        account = await session.scalar(
            select(BankAccount).where(
                BankAccount.company_id == context.company.id,
                BankAccount.id == bank_account_id,
            )
        )
        if account is None:
            raise AccountingNotFound("Bank account was not found")
        if account.branch_id is not None and not context.can_access_branch(
            account.branch_id
        ):
            raise AccountingNotFound("Bank account was not found")
        connection = (
            await session.get(BankConnection, account.connection_id)
            if account.connection_id
            else None
        )
        balance = await session.scalar(
            select(BankBalanceEvidence)
            .where(
                BankBalanceEvidence.company_id == context.company.id,
                BankBalanceEvidence.bank_account_id == account.id,
                func.date(BankBalanceEvidence.balance_as_of) <= cutoff,
            )
            .order_by(BankBalanceEvidence.balance_as_of.desc())
            .limit(1)
        )
        mapping = await session.scalar(
            select(BankAccountGLMapping).where(
                BankAccountGLMapping.company_id == context.company.id,
                BankAccountGLMapping.bank_account_id == account.id,
                BankAccountGLMapping.status == "approved",
            )
        )
        reconciliation = await session.scalar(
            select(BankReconciliation)
            .where(
                BankReconciliation.company_id == context.company.id,
                BankReconciliation.bank_account_id == account.id,
                BankReconciliation.period_end <= cutoff,
            )
            .order_by(BankReconciliation.period_end.desc())
            .limit(1)
        )
        unresolved = int(
            await session.scalar(
                select(func.count(BankTransaction.id))
                .outerjoin(
                    BankTransactionMatch,
                    BankTransactionMatch.bank_transaction_id == BankTransaction.id,
                )
                .where(
                    BankTransaction.company_id == context.company.id,
                    BankTransaction.bank_account_id == account.id,
                    BankTransaction.evidence_status == "active",
                    (
                        BankTransactionMatch.id.is_(None)
                        | BankTransactionMatch.state.in_(
                            (
                                "unmatched",
                                "ambiguous",
                                "review_required",
                                "transfer_candidate",
                            )
                        )
                    ),
                )
            )
            or 0
        )
        blockers: list[str] = []
        if connection is None or connection.status != "healthy":
            blockers.append("CONNECTION_NOT_HEALTHY")
        if mapping is None:
            blockers.append("GL_MAPPING_NOT_APPROVED")
        if balance is None:
            blockers.append("BANK_BALANCE_UNAVAILABLE")
        if reconciliation is None or reconciliation.status != "closed":
            blockers.append("RECONCILIATION_NOT_CLOSED")
        if unresolved:
            blockers.append("UNRESOLVED_BANK_TRANSACTIONS")
        bank_balance = balance.current_balance if balance else None
        book_balance = reconciliation.book_balance if reconciliation else None
        difference = (
            bank_balance - book_balance
            if bank_balance is not None and book_balance is not None
            else None
        )
        provenance = tuple(
            value
            for value in (
                (balance.source_digest if balance else None),
                (mapping.evidence_digest if mapping else None),
                (reconciliation.evidence_digest if reconciliation else None),
            )
            if value
        )
        digest = _digest(
            [account.id, cutoff, provenance, blockers, bank_balance, book_balance]
        )
        return BankAccountingEvidence(
            bank_account_id=account.id,
            display_identity=f"{account.institution_name} {account.account_name} {account.masked_identity}",
            provider=connection.provider if connection else account.source_system,
            connection_status=connection.status if connection else "unmanaged",
            mapped_ledger_account_id=mapping.ledger_account_id if mapping else None,
            mapping_state=mapping.status if mapping else "unmapped",
            bank_current_balance=bank_balance,
            bank_available_balance=balance.available_balance if balance else None,
            bank_balance_as_of=balance.balance_as_of if balance else None,
            book_balance=book_balance,
            cutoff=cutoff,
            unresolved_transaction_count=unresolved,
            reconciliation_status=reconciliation.status
            if reconciliation
            else "unavailable",
            reconciliation_difference=difference,
            readiness="READY" if not blockers and difference == 0 else "BLOCKED",
            blockers=tuple(blockers),
            provenance=provenance,
            evidence_digest=digest,
        )


def _account_type(provider_type: str, subtype: str | None) -> str:
    if provider_type == "depository" and subtype in {
        "checking",
        "savings",
        "money market",
    }:
        return {"money market": "money_market"}.get(subtype or "", subtype or "other")
    return (
        provider_type if provider_type in {"credit", "loan", "investment"} else "other"
    )


bank_connectivity_service = BankConnectivityService()
