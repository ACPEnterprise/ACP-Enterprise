from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.estimates.contracts import CreateEstimateSpec, EstimateLineSpec
from app.estimates.errors import EstimateValidationError
from app.estimates.models import EstimateRevision
from app.estimates.repository import EstimateRepository
from app.estimates.service import EstimateService
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company import membership_models  # noqa: F401
from app.platform.company.models import Company
from app.platform.permissions import models as permission_models  # noqa: F401
from app.platform.users.models import User
from app.price_book.models import (
    PriceBookCategory,
    PriceBookCommercialSnapshot,
    PriceBookPriceVersion,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)


@pytest_asyncio.fixture
async def estimate_fixture():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        company = Company(
            name="Estimate Test",
            code=f"EST{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"E{uuid4().hex[:7].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        actor = User(
            normalized_email=f"estimate-{uuid4().hex}@example.test",
            first_name="Estimate",
            last_name="Owner",
            display_name="Estimate Owner",
            status="active",
        )
        session.add_all([company, branch, actor])
        await session.flush()
        customer = Customer(
            company_id=company.id,
            customer_number=f"CUS-{uuid4().int % 1000000:06d}",
            status="active",
            customer_type="residential",
            display_name="Estimate Customer",
            preferred_contact_method="email",
            normalized_name="estimate customer",
        )
        session.add(customer)
        await session.flush()
        location = ServiceLocation(
            customer_id=customer.id,
            nickname="Home",
            address="1 Test Way",
            city="Test",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address="1 test way test ny 10001 us",
        )
        session.add(location)
        category = PriceBookCategory(
            company_id=company.id,
            code="ESTIMATE",
            name="Estimate",
            status="active",
            version=1,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        tax = PriceBookTaxClassification(
            company_id=company.id,
            code="STANDARD",
            name="Standard",
            taxable=True,
            status="active",
            version=1,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        session.add_all([category, tax])
        await session.flush()
        item = PriceBookServiceItem(
            company_id=company.id,
            branch_id=branch.id,
            category_id=category.id,
            code="EST-SVC",
            name="Estimate Service",
            customer_description="Customer service",
            status="active",
            version=1,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        await session.flush()
        version = PriceBookPriceVersion(
            company_id=company.id,
            branch_id=branch.id,
            service_item_id=item.id,
            revision=1,
            status="active",
            currency="USD",
            unit_price=Decimal("125.00"),
            tax_classification_id=tax.id,
            effective_at=now - timedelta(days=1),
            version=1,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        session.add(version)
        await session.flush()
        snapshot = PriceBookCommercialSnapshot(
            company_id=company.id,
            branch_id=branch.id,
            service_item_id=item.id,
            price_version_id=version.id,
            quantity=Decimal(2),
            unit_price=Decimal("125.00"),
            extended_amount=Decimal("250.00"),
            currency="USD",
            effective_at=now,
            snapshot_data={"customer_description": "Customer service"},
            digest="a" * 64,
            idempotency_key=f"estimate-{uuid4()}",
            created_by_user_id=actor.id,
            created_at=now,
        )
        session.add(snapshot)
        await session.flush()
    try:
        yield factory, company, branch, actor, customer, location, snapshot
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def make_spec(
    company, branch, actor, customer, location, snapshot
) -> CreateEstimateSpec:
    return CreateEstimateSpec(
        company_id=company.id,
        branch_id=branch.id,
        customer_id=customer.id,
        service_location_id=location.id,
        actor_user_id=actor.id,
        proposal_title="Foundation proposal",
        customer_message="Thank you",
        terms="Valid for 30 days",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        lines=(EstimateLineSpec(snapshot_id=snapshot.id, title="Customer service"),),
    )


@pytest.mark.asyncio
async def test_create_uses_immutable_price_book_snapshot(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    async with factory() as session:
        record = await EstimateService().create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
        assert record.estimate_number == "EST-000001"
        assert record.status == "draft"
        assert record.acceptance_status == "not_requested"
        assert record.current_revision.total_amount == Decimal("250.00")
        assert record.current_revision.lines[0].snapshot_id == snapshot.id
        assert record.current_revision.lines[0].snapshot_digest == "a" * 64
        event = await session.scalar(
            select(BusinessEvent).where(BusinessEvent.entity_id == record.id)
        )
        assert event is not None and event.event_type == "estimate.created"


@pytest.mark.asyncio
async def test_company_and_branch_snapshot_scope_fail_closed(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    bad = make_spec(company, branch, actor, customer, location, snapshot)
    bad = replace(bad, branch_id=uuid4())
    async with factory() as session:
        with pytest.raises(EstimateValidationError, match="Company- and Branch-scoped"):
            await EstimateService().create(session, spec=bad)


@pytest.mark.asyncio
async def test_revision_and_lifecycle_evidence_are_database_immutable(
    estimate_fixture,
) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    async with factory() as session:
        record = await EstimateService().create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
        with pytest.raises(DBAPIError, match="immutable"):
            await session.execute(
                update(EstimateRevision)
                .where(EstimateRevision.id == record.current_revision.id)
                .values(proposal_title="Changed")
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_repository_returns_dtos_not_orm_models(estimate_fixture) -> None:
    factory, company, branch, actor, customer, location, snapshot = estimate_fixture
    async with factory() as session:
        created = await EstimateService().create(
            session,
            spec=make_spec(company, branch, actor, customer, location, snapshot),
        )
        loaded = await EstimateRepository.get(
            session, company_id=company.id, estimate_id=created.id
        )
        assert loaded == created
        assert loaded is not None
        assert not hasattr(loaded, "__table__")


@pytest.mark.asyncio
async def test_number_allocation_is_company_scoped(estimate_fixture) -> None:
    factory, company, *_ = estimate_fixture
    async with factory() as session, session.begin():
        assert (
            await EstimateRepository.next_estimate_number(
                session, company_id=company.id
            )
            == "EST-000001"
        )
        assert (
            await EstimateRepository.next_estimate_number(
                session, company_id=company.id
            )
            == "EST-000002"
        )
