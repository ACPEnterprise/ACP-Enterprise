from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import (
    Account,
    AccountingPeriod,
    ChartVersion,
    Journal,
    JournalLine,
    PostingSource,
)
from app.platform.company.models import Company


@dataclass(frozen=True, slots=True)
class ReportingContextFact:
    company_id: UUID
    company_timezone: str
    currency: str
    accounting_basis: str
    chart_version: int


@dataclass(frozen=True, slots=True)
class PeriodFact:
    id: UUID
    name: str
    start_date: date
    end_date: date
    status: str
    version: int


@dataclass(frozen=True, slots=True)
class LedgerLineFact:
    line_id: UUID
    journal_id: UUID
    ordinal: int
    company_id: UUID
    branch_id: UUID | None
    account_id: UUID
    account_code: str
    account_name: str
    classification: str
    normal_balance: str
    account_status: str
    account_effective_from: date
    account_effective_to: date | None
    period_id: UUID
    period_name: str
    period_start_date: date
    period_end_date: date
    period_status: str
    journal_type: str
    journal_status: str
    effective_date: date
    currency: str
    journal_description: str
    line_description: str
    debit: Decimal
    credit: Decimal
    journal_total_debits: Decimal
    journal_total_credits: Decimal
    prepared_by_user_id: UUID
    approved_by_user_id: UUID | None
    posted_at: datetime | None
    source_system: str
    source_type: str
    source_identity: str
    source_digest: str
    posting_rule_version: str
    correlation_id: UUID | None
    reversal_of_id: UUID | None
    journal_version: int


class FinancialReportingRepository:
    async def context(
        self, session: AsyncSession, company_id: UUID
    ) -> ReportingContextFact | None:
        row = (
            await session.execute(
                select(Company, ChartVersion)
                .join(ChartVersion, ChartVersion.company_id == Company.id)
                .where(
                    Company.id == company_id,
                    Company.status == "active",
                    ChartVersion.is_active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        company, chart = row
        return ReportingContextFact(
            company_id=company.id,
            company_timezone=company.timezone,
            currency=chart.currency,
            accounting_basis=chart.accounting_basis,
            chart_version=chart.version,
        )

    async def period(
        self, session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> PeriodFact | None:
        row = await session.scalar(
            select(AccountingPeriod).where(
                AccountingPeriod.company_id == company_id,
                AccountingPeriod.id == period_id,
            )
        )
        if row is None:
            return None
        return PeriodFact(
            id=row.id,
            name=row.name,
            start_date=row.start_date,
            end_date=row.end_date,
            status=row.status,
            version=row.version,
        )

    async def ledger_lines(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        as_of: date,
        branch_id: UUID | None,
    ) -> tuple[LedgerLineFact, ...]:
        query = (
            select(JournalLine, Journal, Account, AccountingPeriod, PostingSource)
            .join(
                Journal,
                (Journal.company_id == JournalLine.company_id)
                & (Journal.id == JournalLine.journal_id),
            )
            .join(
                Account,
                (Account.company_id == JournalLine.company_id)
                & (Account.id == JournalLine.account_id),
            )
            .join(
                AccountingPeriod,
                (AccountingPeriod.company_id == Journal.company_id)
                & (AccountingPeriod.id == Journal.period_id),
            )
            .outerjoin(
                PostingSource,
                (PostingSource.company_id == Journal.company_id)
                & (PostingSource.journal_id == Journal.id),
            )
            .where(
                JournalLine.company_id == company_id,
                Journal.status == "posted",
                Journal.effective_date <= as_of,
            )
            .order_by(
                Journal.effective_date,
                Journal.posted_at,
                Journal.id,
                JournalLine.ordinal,
                JournalLine.id,
            )
        )
        if branch_id is not None:
            query = query.where(JournalLine.branch_id == branch_id)
        rows = await session.execute(query)
        return tuple(
            LedgerLineFact(
                line_id=line.id,
                journal_id=journal.id,
                ordinal=line.ordinal,
                company_id=line.company_id,
                branch_id=line.branch_id,
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                classification=account.classification,
                normal_balance=account.normal_balance,
                account_status=account.status,
                account_effective_from=account.effective_from,
                account_effective_to=account.effective_to,
                period_id=period.id,
                period_name=period.name,
                period_start_date=period.start_date,
                period_end_date=period.end_date,
                period_status=period.status,
                journal_type=journal.journal_type,
                journal_status=journal.status,
                effective_date=journal.effective_date,
                currency=journal.currency,
                journal_description=journal.description,
                line_description=line.description,
                debit=Decimal(line.debit),
                credit=Decimal(line.credit),
                journal_total_debits=Decimal(journal.total_debits),
                journal_total_credits=Decimal(journal.total_credits),
                prepared_by_user_id=journal.prepared_by_user_id,
                approved_by_user_id=journal.approved_by_user_id,
                posted_at=journal.posted_at,
                source_system=journal.source_system,
                source_type=journal.source_type,
                source_identity=journal.source_identity,
                source_digest=journal.source_digest,
                posting_rule_version=journal.posting_rule_version,
                correlation_id=posting_source.correlation_id
                if posting_source is not None
                else None,
                reversal_of_id=journal.reversal_of_id,
                journal_version=journal.version,
            )
            for line, journal, account, period, posting_source in rows
        )


financial_reporting_repository = FinancialReportingRepository()
