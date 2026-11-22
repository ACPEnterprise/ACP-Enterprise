from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from app.core.config import settings
from app.customers.models import Customer
from app.invoicing.models import Invoice, ManualPaymentReceipt
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.onboarding.preview_tenant_fixture import (
    FIXTURE_BRANCH_CODE,
    FIXTURE_BRANCH_ID,
    FIXTURE_BRANCH_NAME,
    FIXTURE_COMPANY_CODE,
    FIXTURE_COMPANY_ID,
    FIXTURE_COMPANY_NAME,
    FIXTURE_VERSION,
    PreviewSyntheticTenantCommand,
    PreviewSyntheticTenantFixtureService,
)
from app.platform.onboarding.sales_forward_fixture import (
    FIXTURE_CUSTOMER_ID,
    FIXTURE_INVOICE_ID,
    FIXTURE_RECEIPT_ID,
    SALES_FORWARD_BRANCH_ID,
    SALES_FORWARD_COMPANY_ID,
    SALES_FORWARD_COMPANY_NAME,
    SALES_FORWARD_FIXTURE_VERSION,
    SalesForwardFixtureCommand,
    SalesForwardFixtureService,
)
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.codes import AdministrationPermission
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class Session:
    def __init__(self):
        self.records = {}
        self.execute = AsyncMock()

    def begin(self):
        return Transaction()

    async def get(self, model, identity):
        return self.records.get((model, identity))

    def add(self, value):
        self.records[(type(value), value.id)] = value

    async def flush(self):
        return None


def configuration(environment="preview", enabled=True):
    return SimpleNamespace(
        environment=environment,
        preview_acceptance_fixture_enabled=enabled,
    )


def context(*permissions):
    if not permissions:
        permissions = (
            AdministrationPermission.COMPANY_ADMINISTER,
            AdministrationPermission.IDENTITY_ONBOARDING_MANAGE,
        )
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        permission_codes=frozenset(permissions),
    )


def audit_service():
    service = Mock()
    service.stage.side_effect = lambda *_args: SimpleNamespace(id=uuid4())
    return service


def service(environment="preview"):
    auditing = audit_service()
    return SalesForwardFixtureService(
        configuration=configuration(environment), auditing=auditing
    ), auditing


@pytest.mark.asyncio
async def test_sales_forward_fixture_fails_closed_outside_preview():
    fixture, _ = service("production")
    session = Session()

    with pytest.raises(OnboardingConflictError):
        await fixture.create_or_reuse(
            session,
            context=context(),
            command=SalesForwardFixtureCommand(
                fixture_version=SALES_FORWARD_FIXTURE_VERSION,
                authorized=True,
            ),
        )

    session.execute.assert_not_awaited()
    assert session.records == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,authorized,version,caller",
    [
        (False, True, SALES_FORWARD_FIXTURE_VERSION, context()),
        (True, False, SALES_FORWARD_FIXTURE_VERSION, context()),
        (True, True, "wrong.fixture", context()),
        (
            True,
            True,
            SALES_FORWARD_FIXTURE_VERSION,
            context(AdministrationPermission.COMPANY_ADMINISTER),
        ),
    ],
)
async def test_sales_forward_fixture_requires_explicit_authority(
    enabled, authorized, version, caller
):
    auditing = audit_service()
    fixture = SalesForwardFixtureService(
        configuration=configuration(enabled=enabled), auditing=auditing
    )
    session = Session()

    with pytest.raises(OnboardingConflictError):
        await fixture.create_or_reuse(
            session,
            context=caller,
            command=SalesForwardFixtureCommand(version, authorized),
        )

    session.execute.assert_not_awaited()
    assert session.records == {}


@pytest.mark.asyncio
async def test_sales_forward_fixture_is_idempotent_and_non_money():
    fixture, auditing = service()
    session = Session()
    command = SalesForwardFixtureCommand(SALES_FORWARD_FIXTURE_VERSION, True)

    first = await fixture.create_or_reuse(session, context=context(), command=command)
    record_count = len(session.records)
    second = await fixture.create_or_reuse(session, context=context(), command=command)

    assert first.action == "created"
    assert second.action == "reused"
    assert len(session.records) == record_count
    company = session.records[(Company, SALES_FORWARD_COMPANY_ID)]
    branch = session.records[(Branch, SALES_FORWARD_BRANCH_ID)]
    assert company.name == SALES_FORWARD_COMPANY_NAME
    assert company.id != FIXTURE_COMPANY_ID
    assert branch.company_id == company.id
    invoice = session.records[(Invoice, FIXTURE_INVOICE_ID)]
    receipt = session.records[(ManualPaymentReceipt, FIXTURE_RECEIPT_ID)]
    assert invoice.open_amount == invoice.total_amount
    assert receipt.settlement_state == "not_asserted"
    assert receipt.accounting_state == "not_posted"
    entry = auditing.stage.call_args.args[1]
    assert entry.details["provider_writes"] is False
    assert entry.details["money_movement"] is False


@pytest.mark.asyncio
async def test_sales_forward_tenant_is_isolated_from_existing_acp_fixture():
    fixture, _ = service()
    session = Session()
    acp_company = Company(
        id=FIXTURE_COMPANY_ID,
        name=FIXTURE_COMPANY_NAME,
        code=FIXTURE_COMPANY_CODE,
        status="active",
        timezone="America/New_York",
    )
    acp_branch = Branch(
        id=FIXTURE_BRANCH_ID,
        company_id=FIXTURE_COMPANY_ID,
        name=FIXTURE_BRANCH_NAME,
        code=FIXTURE_BRANCH_CODE,
        status="active",
        timezone="America/New_York",
        is_primary=True,
    )
    session.add(acp_company)
    session.add(acp_branch)

    result = await fixture.create_or_reuse(
        session,
        context=context(),
        command=SalesForwardFixtureCommand(SALES_FORWARD_FIXTURE_VERSION, True),
    )

    assert result.company_id == SALES_FORWARD_COMPANY_ID
    assert result.branch_id == SALES_FORWARD_BRANCH_ID
    assert session.records[(Company, FIXTURE_COMPANY_ID)] is acp_company
    assert session.records[(Branch, FIXTURE_BRANCH_ID)] is acp_branch
    customer = session.records[(Customer, FIXTURE_CUSTOMER_ID)]
    assert customer.company_id == SALES_FORWARD_COMPANY_ID


@pytest.mark.asyncio
async def test_sales_forward_fixture_rejects_cross_tenant_identity_collision():
    fixture, _ = service()
    session = Session()
    command = SalesForwardFixtureCommand(SALES_FORWARD_FIXTURE_VERSION, True)
    await fixture.create_or_reuse(session, context=context(), command=command)
    customer = session.records[(Customer, FIXTURE_CUSTOMER_ID)]
    customer.company_id = uuid4()

    with pytest.raises(OnboardingConflictError, match="Customer state"):
        await fixture.create_or_reuse(
            session,
            context=context(),
            command=command,
        )


@pytest.mark.asyncio
async def test_sales_forward_fixture_rejects_material_financial_drift():
    fixture, _ = service()
    session = Session()
    command = SalesForwardFixtureCommand(SALES_FORWARD_FIXTURE_VERSION, True)
    await fixture.create_or_reuse(session, context=context(), command=command)
    invoice = session.records[(Invoice, FIXTURE_INVOICE_ID)]
    invoice.open_amount = Decimal("0.00")

    with pytest.raises(OnboardingConflictError, match="Invoice state"):
        await fixture.create_or_reuse(
            session,
            context=context(),
            command=command,
        )


@pytest.mark.asyncio
async def test_sales_forward_fixture_persists_one_connected_postgresql_scenario():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture, _ = service()
    tenant_fixture = PreviewSyntheticTenantFixtureService(
        configuration=configuration(), auditing=audit_service()
    )
    command = SalesForwardFixtureCommand(SALES_FORWARD_FIXTURE_VERSION, True)

    async with factory() as session:
        await tenant_fixture.create_or_reuse(
            session,
            context=context(),
            command=PreviewSyntheticTenantCommand(FIXTURE_VERSION, True),
        )
    async with factory() as session:
        first = await fixture.create_or_reuse(
            session, context=context(), command=command
        )
    async with factory() as session:
        second = await fixture.create_or_reuse(
            session, context=context(), command=command
        )

    assert first.action in {"created", "reused"}
    assert second.action == "reused"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.id == FIXTURE_CUSTOMER_ID)
            )
            == 1
        )
        invoice = await session.get(Invoice, FIXTURE_INVOICE_ID)
        receipt = await session.get(ManualPaymentReceipt, FIXTURE_RECEIPT_ID)
        sales_company = await session.get(Company, SALES_FORWARD_COMPANY_ID)
        acp_company = await session.get(Company, FIXTURE_COMPANY_ID)
        customer = await session.get(Customer, FIXTURE_CUSTOMER_ID)
        assert invoice is not None
        assert receipt is not None
        assert sales_company is not None
        assert acp_company is not None
        assert customer is not None
        assert sales_company.name == SALES_FORWARD_COMPANY_NAME
        assert sales_company.id != acp_company.id
        assert acp_company.name == FIXTURE_COMPANY_NAME
        assert customer.company_id == sales_company.id
        assert invoice.customer_id == FIXTURE_CUSTOMER_ID
        assert receipt.invoice_id == invoice.id
        assert receipt.settlement_state == "not_asserted"
        assert receipt.accounting_state == "not_posted"
    await engine.dispose()
