from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import (
    Account,
    AccountingPeriod,
    ChartVersion,
    ControlAccountAssignment,
    Journal,
    JournalLine,
    PostingSource,
)


class AccountingRepository:
    async def active_chart(
        self, session: AsyncSession, company_id: UUID
    ) -> ChartVersion | None:
        return await session.scalar(
            select(ChartVersion)
            .where(
                ChartVersion.company_id == company_id, ChartVersion.is_active.is_(True)
            )
            .with_for_update()
        )

    async def list_accounts(
        self, session: AsyncSession, company_id: UUID
    ) -> tuple[Account, ...]:
        rows = await session.scalars(
            select(Account)
            .where(Account.company_id == company_id)
            .order_by(Account.code)
        )
        return tuple(rows.all())

    async def account(
        self, session: AsyncSession, company_id: UUID, account_id: UUID
    ) -> Account | None:
        return await session.scalar(
            select(Account).where(
                Account.company_id == company_id, Account.id == account_id
            )
        )

    async def control_account_ids(
        self, session: AsyncSession, company_id: UUID, effective_date: date
    ) -> frozenset[UUID]:
        rows = await session.scalars(
            select(ControlAccountAssignment.account_id).where(
                ControlAccountAssignment.company_id == company_id,
                ControlAccountAssignment.effective_from <= effective_date,
                (
                    ControlAccountAssignment.effective_to.is_(None)
                    | (ControlAccountAssignment.effective_to >= effective_date)
                ),
            )
        )
        return frozenset(rows.all())

    async def period(
        self,
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        *,
        lock: bool = False,
    ) -> AccountingPeriod | None:
        query = select(AccountingPeriod).where(
            AccountingPeriod.company_id == company_id, AccountingPeriod.id == period_id
        )
        if lock:
            query = query.with_for_update()
        return await session.scalar(query)

    async def list_periods(
        self, session: AsyncSession, company_id: UUID
    ) -> tuple[AccountingPeriod, ...]:
        rows = await session.scalars(
            select(AccountingPeriod)
            .where(AccountingPeriod.company_id == company_id)
            .order_by(AccountingPeriod.start_date)
        )
        return tuple(rows.all())

    async def journal(
        self,
        session: AsyncSession,
        company_id: UUID,
        journal_id: UUID,
        *,
        lock: bool = False,
    ) -> Journal | None:
        query = select(Journal).where(
            Journal.company_id == company_id, Journal.id == journal_id
        )
        if lock:
            query = query.with_for_update()
        return await session.scalar(query)

    async def journal_by_client_key(
        self, session: AsyncSession, company_id: UUID, key: str
    ) -> Journal | None:
        return await session.scalar(
            select(Journal).where(
                Journal.company_id == company_id, Journal.client_idempotency_key == key
            )
        )

    async def posting_source(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_type: str,
        source_identity: str,
        posting_rule_version: str,
    ) -> PostingSource | None:
        return await session.scalar(
            select(PostingSource).where(
                PostingSource.company_id == company_id,
                PostingSource.source_system == source_system,
                PostingSource.source_type == source_type,
                PostingSource.source_identity == source_identity,
                PostingSource.posting_rule_version == posting_rule_version,
            )
        )

    async def lines(
        self, session: AsyncSession, company_id: UUID, journal_id: UUID
    ) -> tuple[JournalLine, ...]:
        rows = await session.scalars(
            select(JournalLine)
            .where(
                JournalLine.company_id == company_id,
                JournalLine.journal_id == journal_id,
            )
            .order_by(JournalLine.ordinal)
        )
        return tuple(rows.all())

    async def trial_balance(
        self, session: AsyncSession, company_id: UUID, *, through: date | None = None
    ) -> tuple[Decimal, Decimal]:
        query = (
            select(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(
                Journal,
                (Journal.company_id == JournalLine.company_id)
                & (Journal.id == JournalLine.journal_id),
            )
            .where(Journal.company_id == company_id, Journal.status == "posted")
        )
        if through is not None:
            query = query.where(Journal.effective_date <= through)
        row = (await session.execute(query)).one()
        return Decimal(row[0]), Decimal(row[1])


accounting_repository = AccountingRepository()
