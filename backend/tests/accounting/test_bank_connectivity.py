from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.accounting.bank_connectivity import (
    BankConnectivityService,
    ConnectionCreate,
    PlaidReadOnlyAdapter,
    ProviderAccount,
    ProviderSyncPage,
    ProviderTransaction,
)
from app.accounting.models import (
    Account,
    BankAccount,
    BankBalanceEvidence,
    BankConnection,
    BankTransaction,
    BankTransactionEvidenceVersion,
    ChartVersion,
)
from app.core.config import settings
from app.customers import models as customer_models  # noqa: F401
from app.platform.audit import models as audit_models  # noqa: F401
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User

NOW = datetime(2026, 10, 5, 14, 30, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], str]] = []

    async def post(
        self, path: str, payload: dict[str, object], *, access_token: str
    ) -> dict[str, object]:
        self.calls.append((path, payload, access_token))
        if path == "/accounts/balance/get":
            return {
                "accounts": [
                    {
                        "account_id": "provider-account-1",
                        "name": "Operating",
                        "official_name": "Operating Checking",
                        "type": "depository",
                        "subtype": "checking",
                        "mask": "1234",
                        "balances": {
                            "current": 1250.50,
                            "available": 1200.25,
                            "iso_currency_code": "USD",
                        },
                    }
                ]
            }
        return {
            "added": [],
            "modified": [],
            "removed": [],
            "next_cursor": "cursor-1",
            "has_more": False,
            "request_id": "request-1",
        }


@pytest.mark.asyncio
async def test_plaid_adapter_uses_balance_and_incremental_sync_contract() -> None:
    transport = FakeTransport()
    adapter = PlaidReadOnlyAdapter(transport)

    accounts = await adapter.accounts("runtime-token")
    page = await adapter.transaction_page("runtime-token", "cursor-0")

    assert accounts[0].provider_account_id == "provider-account-1"
    assert accounts[0].current_balance == Decimal("1250.5")
    assert accounts[0].available_balance == Decimal("1200.25")
    assert page.next_cursor == "cursor-1"
    assert transport.calls == [
        ("/accounts/balance/get", {}, "runtime-token"),
        (
            "/transactions/sync",
            {"count": 500, "cursor": "cursor-0"},
            "runtime-token",
        ),
    ]


class FixtureResolver:
    def __init__(self) -> None:
        self.references: list[str] = []

    async def resolve(self, credential_reference: str) -> str:
        self.references.append(credential_reference)
        return "ephemeral-provider-token"


class SequenceAdapter:
    provider = "plaid"

    def __init__(self) -> None:
        self.phase = 0

    async def accounts(self, access_token: str) -> tuple[ProviderAccount, ...]:
        assert access_token == "ephemeral-provider-token"
        return (
            ProviderAccount(
                provider_account_id="provider-account-1",
                name="Operating",
                official_name="Operating Checking",
                account_type="depository",
                subtype="checking",
                mask="1234",
                currency="USD",
                current_balance=Decimal("850.00"),
                available_balance=Decimal("825.00"),
                balance_as_of=NOW,
            ),
        )

    async def transaction_page(
        self, access_token: str, cursor: str | None
    ) -> ProviderSyncPage:
        assert access_token == "ephemeral-provider-token"
        self.phase += 1
        if self.phase == 1:
            transaction = ProviderTransaction(
                provider_transaction_id="pending-1",
                provider_account_id="provider-account-1",
                pending=True,
                transaction_date=date(2026, 10, 4),
                amount=Decimal("25.00"),
                currency="USD",
                name="Pending sanitized purchase",
            )
        else:
            transaction = ProviderTransaction(
                provider_transaction_id="posted-1",
                provider_account_id="provider-account-1",
                pending_transaction_id="pending-1",
                pending=False,
                transaction_date=date(2026, 10, 5),
                authorized_date=date(2026, 10, 4),
                amount=Decimal("30.00" if self.phase == 4 else "25.00"),
                currency="USD",
                name="Posted sanitized purchase",
            )
        return ProviderSyncPage(
            added=(transaction,) if self.phase < 4 else (),
            modified=(transaction,) if self.phase == 4 else (),
            removed=(
                ({"provider_transaction_id": "posted-1"},)
                if self.phase == 5
                else ()
            ),
            next_cursor=f"cursor-{self.phase}",
            has_more=False,
            source_as_of=NOW,
        )


@pytest_asyncio.fixture
async def connectivity_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Bank connectivity fixture",
            code=f"BC{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"B{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        user = User(
            normalized_email=f"bank-{uuid4().hex}@example.test",
            first_name="Bank",
            last_name="Reviewer",
            display_name="Bank Reviewer",
            status="active",
        )
        session.add_all((company, branch, user))
        await session.flush()
        chart = ChartVersion(
            company_id=company.id,
            version=1,
            name="Bank fixture chart",
            currency="USD",
            accounting_basis="accrual",
            source_checksum="a" * 64,
            effective_at=NOW,
            is_active=True,
            approved_by_user_id=user.id,
        )
        session.add(chart)
        await session.flush()
        ledger = Account(
            company_id=company.id,
            chart_version_id=chart.id,
            code="1010",
            name="Operating cash",
            classification="asset",
            normal_balance="debit",
            status="active",
            effective_from=date(2026, 10, 1),
        )
        session.add(ledger)
        await session.flush()
    context = SimpleNamespace(
        company=company,
        user=user,
        can_access_branch=lambda branch_id: branch_id == branch.id,
    )
    try:
        yield factory, context, branch, ledger
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sync_is_replay_safe_and_preserves_pending_posted_lineage(
    connectivity_fixture,
) -> None:
    factory, context, branch, _ledger = connectivity_fixture
    service = BankConnectivityService()
    adapter = SequenceAdapter()
    resolver = FixtureResolver()
    async with factory() as session, session.begin():
        connection = await service.create_connection(
            session,
            context=context,
            request=ConnectionCreate(
                provider="plaid",
                provider_institution_id="institution-1",
                provider_connection_id=f"item-{uuid4()}",
                institution_name="Fixture Financial",
                credential_reference="secret://banking/fixture-token",
                branch_id=branch.id,
                provider_version="transactions-sync-v1",
                source_digest="b" * 64,
            ),
        )
        connection_id = connection.id

    async with factory() as session, session.begin():
        first = await service.synchronize(
            session,
            context=context,
            connection_id=connection_id,
            adapter=adapter,
            resolver=resolver,
        )
        assert first.added == 1
    async with factory() as session, session.begin():
        second = await service.synchronize(
            session,
            context=context,
            connection_id=connection_id,
            adapter=adapter,
            resolver=resolver,
        )
    async with factory() as session, session.begin():
        replay = await service.synchronize(
            session,
            context=context,
            connection_id=connection_id,
            adapter=adapter,
            resolver=resolver,
        )
    async with factory() as session, session.begin():
        modified = await service.synchronize(
            session,
            context=context,
            connection_id=connection_id,
            adapter=adapter,
            resolver=resolver,
        )
    async with factory() as session, session.begin():
        removed = await service.synchronize(
            session,
            context=context,
            connection_id=connection_id,
            adapter=adapter,
            resolver=resolver,
        )

    async with factory() as session:
        transactions = tuple(
            (
                await session.scalars(
                    select(BankTransaction)
                    .where(BankTransaction.company_id == context.company.id)
                    .order_by(BankTransaction.external_transaction_id)
                )
            ).all()
        )
        assert len(transactions) == 2
        pending = next(row for row in transactions if row.state == "pending")
        posted = next(row for row in transactions if row.state == "posted")
        assert pending.evidence_status == "superseded"
        assert posted.pending_transaction_id == pending.external_transaction_id
        assert second.added == 1
        assert replay.replayed == 1
        assert modified.modified == 1
        assert removed.removed == 1
        assert posted.amount == Decimal("30.00")
        assert posted.evidence_status == "removed"
        assert (
            await session.scalar(
                select(func.count(BankBalanceEvidence.id)).where(
                    BankBalanceEvidence.company_id == context.company.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BankTransactionEvidenceVersion.id)).where(
                    BankTransactionEvidenceVersion.company_id == context.company.id
                )
            )
            == 4
        )
        stored_connection = await session.get(BankConnection, connection_id)
        assert stored_connection is not None
        assert (
            stored_connection.credential_reference == "secret://banking/fixture-token"
        )
        assert "ephemeral-provider-token" not in stored_connection.credential_reference
        assert stored_connection.status == "healthy"
        account = await session.scalar(
            select(BankAccount).where(BankAccount.connection_id == connection_id)
        )
        assert account is not None
        assert account.masked_identity == "••••1234"
    assert resolver.references == ["secret://banking/fixture-token"] * 5


@pytest.mark.asyncio
async def test_bank_connectivity_is_company_scoped(connectivity_fixture) -> None:
    factory, context, branch, _ledger = connectivity_fixture
    service = BankConnectivityService()
    async with factory() as session, session.begin():
        connection = await service.create_connection(
            session,
            context=context,
            request=ConnectionCreate(
                provider="plaid",
                provider_institution_id="institution-isolation",
                provider_connection_id=f"item-{uuid4()}",
                institution_name="Isolation Financial",
                credential_reference="secret://banking/isolation-token",
                branch_id=branch.id,
                source_digest="c" * 64,
            ),
        )
    other_context = SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        user=context.user,
        can_access_branch=lambda _branch_id: False,
    )
    async with factory() as session:
        with pytest.raises(Exception, match="not found"):
            await service.synchronize(
                session,
                context=other_context,
                connection_id=connection.id,
                adapter=SequenceAdapter(),
                resolver=FixtureResolver(),
            )
