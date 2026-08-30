import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounting.errors import AccountingConflict
from app.accounting.models import (
    Account,
    AccountingPeriod,
    ChartVersion,
    Journal,
    PostingSource,
)
from app.accounting.schemas import JournalCreate, JournalLineCreate, ReversalCreate
from app.accounting.service import AccountingService
from app.core.config import settings
from app.customers import models as customer_models  # noqa: F401
from app.events.models import BusinessEvent
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User
from app.scheduling import models as scheduling_models  # noqa: F401


@pytest_asyncio.fixture
async def accounting_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = date(2026, 8, 30)
    async with factory() as session, session.begin():
        company = Company(
            name="Accounting concurrency",
            code=f"ACC{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"A{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        users = [
            User(
                normalized_email=f"accounting-{index}-{uuid4().hex}@example.test",
                first_name=f"Actor{index}",
                last_name="Accounting",
                display_name=f"Accounting Actor {index}",
                status="active",
            )
            for index in range(3)
        ]
        session.add_all([company, branch, *users])
        await session.flush()
        chart = ChartVersion(
            company_id=company.id,
            version=1,
            name="Synthetic chart",
            currency="USD",
            accounting_basis="accrual",
            source_checksum="1" * 64,
            effective_at=datetime.now(timezone.utc),
            is_active=True,
            approved_by_user_id=users[0].id,
        )
        period = AccountingPeriod(
            company_id=company.id,
            name="August 2026",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            status="open",
            version=1,
            created_by_user_id=users[0].id,
        )
        session.add_all([chart, period])
        await session.flush()
        accounts = (
            Account(
                company_id=company.id,
                chart_version_id=chart.id,
                code="1000",
                name="Synthetic cash",
                classification="asset",
                normal_balance="debit",
                status="active",
                effective_from=today,
            ),
            Account(
                company_id=company.id,
                chart_version_id=chart.id,
                code="4000",
                name="Synthetic revenue",
                classification="revenue",
                normal_balance="credit",
                status="active",
                effective_from=today,
            ),
        )
        session.add_all(accounts)
        await session.flush()

    def context(user):
        return SimpleNamespace(
            company=company,
            user=user,
            can_access_branch=lambda branch_id: branch_id == branch.id,
        )

    try:
        yield factory, company, branch, tuple(map(context, users)), period, accounts
    finally:
        await engine.dispose()


def journal_command(company, branch, period, accounts, *, key: str) -> JournalCreate:
    return JournalCreate(
        period_id=period.id,
        journal_type="manual",
        effective_date=date(2026, 8, 30),
        currency="USD",
        description="Synthetic balanced evidence",
        source_system="qualification",
        source_type="balanced_rehearsal",
        source_identity=f"source-{company.id}",
        source_digest="2" * 64,
        posting_rule_version="qualification-v1",
        client_idempotency_key=key,
        lines=(
            JournalLineCreate(
                account_id=accounts[0].id,
                branch_id=branch.id,
                debit=Decimal("75.25"),
                description="Synthetic debit",
            ),
            JournalLineCreate(
                account_id=accounts[1].id,
                branch_id=branch.id,
                credit=Decimal("75.25"),
                description="Synthetic credit",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_concurrent_journal_create_post_and_reversal_have_one_authority(
    accounting_fixture,
) -> None:
    factory, company, branch, contexts, period, accounts = accounting_fixture
    service = AccountingService()
    command = journal_command(
        company, branch, period, accounts, key=f"journal-{uuid4()}"
    )

    async def create():
        async with factory() as session:
            return await service.create_journal(
                session, context=contexts[0], data=command
            )

    first, replay = await asyncio.gather(create(), create())
    assert first.id == replay.id
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Journal.id)).where(
                    Journal.company_id == company.id,
                    Journal.client_idempotency_key == command.client_idempotency_key,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(PostingSource.id)).where(
                    PostingSource.journal_id == first.id
                )
            )
            == 1
        )

    async with factory() as session:
        prepared = await service.prepare_journal(
            session,
            context=contexts[0],
            journal_id=first.id,
            expected_version=first.version,
        )
    async with factory() as session:
        approved = await service.approve_journal(
            session,
            context=contexts[1],
            journal_id=first.id,
            expected_version=prepared.version,
            evidence_digest="3" * 64,
            reason="Independent synthetic approval",
        )

    async def post():
        async with factory() as session:
            return await service.post_journal(
                session,
                context=contexts[2],
                journal_id=first.id,
                expected_version=approved.version,
            )

    post_results = await asyncio.gather(post(), post(), return_exceptions=True)
    assert sum(isinstance(result, Journal) for result in post_results) == 1
    assert sum(isinstance(result, AccountingConflict) for result in post_results) == 1
    async with factory() as session:
        posted = await session.get(Journal, first.id)
        event_count = await session.scalar(
            select(func.count(BusinessEvent.id)).where(
                BusinessEvent.entity_id == first.id,
                BusinessEvent.event_type == "accounting.journal_posted",
            )
        )
    assert posted is not None
    assert posted.status == "posted"
    assert posted.total_debits == posted.total_credits == Decimal("75.2500")
    assert event_count == 1

    reversal = ReversalCreate(
        effective_date=date(2026, 8, 30),
        period_id=period.id,
        client_idempotency_key=f"reversal-{uuid4()}",
        source_digest="4" * 64,
        evidence_digest="5" * 64,
        reason="Synthetic correction",
    )

    async def reverse():
        async with factory() as session:
            return await service.reverse_journal(
                session,
                context=contexts[0],
                journal_id=first.id,
                data=reversal,
            )

    first_reversal, reversal_replay = await asyncio.gather(reverse(), reverse())
    assert first_reversal.id == reversal_replay.id
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(Journal.id)).where(
                    Journal.reversal_of_id == first.id
                )
            )
            == 1
        )
