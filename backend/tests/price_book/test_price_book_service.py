import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import PriceBookPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from app.price_book.errors import PriceBookConflict, PriceBookNotFound
from app.price_book.models import PriceBookAuditEntry, PriceBookCommercialSnapshot
from app.price_book.router import router as price_book_router
from app.price_book.schemas import (
    CategoryCreate,
    ComponentCreate,
    OptionCreate,
    OptionGroupCreate,
    PriceVersionCreate,
    PriceVersionUpdate,
    ServiceItemCreate,
    SnapshotRequest,
    TaxClassificationCreate,
)
from app.price_book.service import PriceBookService
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def price_book_fixture() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], AuthorizationContext, Branch]
]:
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        company = Company(
            name="Price Book Test",
            code=f"PB{uuid4().hex[:8].upper()}",
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
        actor = User(
            normalized_email=f"price-{uuid4().hex}@example.test",
            first_name="Price",
            last_name="Owner",
            display_name="Price Owner",
            status="active",
        )
        session.add_all([company, branch, actor])
        await session.flush()
    membership = Membership(
        id=uuid4(),
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=True,
        created_at=now,
        updated_at=now,
    )
    context = AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=actor.authorization_version,
    )
    try:
        yield factory, context, branch
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def concurrent_price_book_fixture():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        company = Company(
            name="Concurrent Price Book",
            code=f"PBC{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"BC{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        actor = User(
            normalized_email=f"price-concurrent-{uuid4().hex}@example.test",
            first_name="Concurrent",
            last_name="Owner",
            display_name="Concurrent Owner",
            status="active",
        )
        session.add_all([company, branch, actor])
        await session.flush()
    membership = Membership(
        id=uuid4(),
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=True,
        created_at=now,
        updated_at=now,
    )
    context = AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=actor.authorization_version,
    )
    try:
        yield factory, context, branch
    finally:
        await engine.dispose()


async def seed_draft(factory, context, branch):
    service = PriceBookService()
    async with factory() as session:
        category = await service.create_category(
            session,
            context=context,
            payload=CategoryCreate(code="DRAIN", name="Drain Services"),
        )
    async with factory() as session:
        tax = await service.create_tax(
            session,
            context=context,
            payload=TaxClassificationCreate(
                code="TAXABLE", name="Taxable", taxable=True
            ),
        )
    async with factory() as session:
        item = await service.create_item(
            session,
            context=context,
            payload=ServiceItemCreate(
                category_id=category.id,
                code="DRAIN-CLEAR",
                name="Drain clearing",
                customer_description="Clear one standard drain.",
                branch_id=None,
            ),
        )
    effective = datetime.now(timezone.utc) + timedelta(hours=1)
    async with factory() as session:
        version = await service.create_version(
            session,
            context=context,
            item_id=item.id,
            payload=PriceVersionCreate(
                branch_id=None,
                tax_classification_id=tax.id,
                currency="USD",
                unit_price=Decimal("149.9500"),
                effective_at=effective,
                components=(
                    ComponentCreate(
                        component_type="labor",
                        code="LABOR",
                        label="Technician labor",
                        quantity=Decimal("1.5"),
                        unit_cost=Decimal(45),
                    ),
                    ComponentCreate(
                        component_type="material",
                        code="SUPPLY",
                        label="Drain supplies",
                        quantity=Decimal(1),
                        unit_cost=Decimal("8.25"),
                    ),
                ),
            ),
        )
    return service, item, version, effective


@pytest.mark.asyncio
async def test_activation_snapshot_idempotency_and_immutable_history(
    price_book_fixture,
):
    factory, context, branch = price_book_fixture
    service, item, version, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        active = await service.activate(
            session,
            context=context,
            version_id=version.id,
            expected_version=1,
            reason="Approved launch price",
        )
    assert active.status == "active" and active.version == 2
    request = SnapshotRequest(
        branch_id=branch.id,
        quantity=Decimal(2),
        currency="USD",
        effective_at=effective + timedelta(minutes=1),
        idempotency_key="price-snapshot-001",
    )
    async with factory() as session:
        first = await service.snapshot(
            session, context=context, item_id=item.id, payload=request
        )
    async with factory() as session:
        duplicate = await service.snapshot(
            session, context=context, item_id=item.id, payload=request
        )
    assert first.id == duplicate.id
    assert first.extended_amount == Decimal("299.90")
    assert first.snapshot_data["components"][0]["type"] == "labor"
    async with factory() as session:
        public_catalog = await service.catalog(session, context=context)
    serialized_catalog = public_catalog.model_dump(mode="json")
    assert "unit_cost" not in str(serialized_catalog)
    assert "internal_description" not in str(serialized_catalog)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PriceBookCommercialSnapshot)
                .where(PriceBookCommercialSnapshot.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(PriceBookAuditEntry))
            >= 6
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.event_type == "price_book.price_version_activated",
                    BusinessEvent.company_id == context.company.id,
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_activation_supersedes_transactionally_and_rejects_stale_version(
    price_book_fixture,
):
    factory, context, branch = price_book_fixture
    service, item, first, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=first.id,
            expected_version=1,
            reason="Initial",
        )
    async with factory() as session:
        catalog = await service.catalog(session, context=context)
        tax_id = catalog.tax_classifications[0].id
    async with factory() as session:
        second = await service.create_version(
            session,
            context=context,
            item_id=item.id,
            payload=PriceVersionCreate(
                tax_classification_id=tax_id,
                currency="USD",
                unit_price=Decimal(159),
                effective_at=effective + timedelta(days=1),
            ),
        )
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=second.id,
            expected_version=1,
            reason="Annual update",
        )
    async with factory() as session:
        catalog = await service.catalog(session, context=context)
    versions = {record.id: record for record in catalog.versions}
    assert versions[first.id].status == "superseded"
    assert versions[first.id].expires_at == second.effective_at
    assert versions[second.id].status == "active"
    async with factory() as session:
        with pytest.raises((PriceBookConflict, PriceBookNotFound)):
            await service.activate(
                session,
                context=context,
                version_id=second.id,
                expected_version=1,
                reason="Duplicate",
            )


@pytest.mark.asyncio
async def test_branch_and_company_scope_fail_closed(price_book_fixture):
    factory, context, branch = price_book_fixture
    service, item, version, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=version.id,
            expected_version=1,
            reason="Launch",
        )
    with pytest.raises(PriceBookNotFound):
        async with factory() as session:
            await service.snapshot(
                session,
                context=context,
                item_id=item.id,
                payload=SnapshotRequest(
                    branch_id=uuid4(),
                    quantity=Decimal(1),
                    currency="USD",
                    effective_at=effective + timedelta(minutes=1),
                    idempotency_key="wrong-branch-001",
                ),
            )
    with pytest.raises(PriceBookConflict):
        async with factory() as session:
            await service.snapshot(
                session,
                context=context,
                item_id=item.id,
                payload=SnapshotRequest(
                    branch_id=branch.id,
                    quantity=Decimal(1),
                    currency="EUR",
                    effective_at=effective + timedelta(minutes=1),
                    idempotency_key="wrong-currency-01",
                ),
            )
    wrong_company_id = uuid4()
    wrong_context = AuthorizationContext(
        user=context.user,
        company=replace(context.company, id=wrong_company_id, code="WRONGCOMPANY"),
        membership=replace(context.membership, company_id=wrong_company_id),
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=(),
        credential_version=context.credential_version,
        authorization_version=context.authorization_version,
    )
    with pytest.raises(PriceBookNotFound):
        async with factory() as session:
            await service.snapshot(
                session,
                context=wrong_context,
                item_id=item.id,
                payload=SnapshotRequest(
                    branch_id=branch.id,
                    quantity=Decimal(1),
                    currency="USD",
                    effective_at=effective + timedelta(minutes=1),
                    idempotency_key="wrong-company-01",
                ),
            )


@pytest.mark.asyncio
async def test_customer_options_and_snapshot_idempotency_collision_fail_closed(
    price_book_fixture,
):
    factory, context, branch = price_book_fixture
    service, item, version, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        group = await service.create_option_group(
            session,
            context=context,
            payload=OptionGroupCreate(code="SERVICE-LEVEL", name="Service level"),
        )
    async with factory() as session:
        option = await service.add_option(
            session,
            context=context,
            group_id=group.id,
            payload=OptionCreate(service_item_id=item.id, label="Standard", position=1),
        )
    async with factory() as session:
        catalog = await service.catalog(session, context=context)
    assert catalog.option_groups[0].id == group.id
    assert catalog.options[0].id == option.id
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=version.id,
            expected_version=1,
            reason="Launch",
        )
    first_request = SnapshotRequest(
        branch_id=branch.id,
        quantity=Decimal(1),
        currency="USD",
        effective_at=effective + timedelta(minutes=1),
        idempotency_key="collision-check-001",
    )
    async with factory() as session:
        await service.snapshot(
            session, context=context, item_id=item.id, payload=first_request
        )
    with pytest.raises(PriceBookConflict):
        async with factory() as session:
            await service.snapshot(
                session,
                context=context,
                item_id=item.id,
                payload=first_request.model_copy(update={"quantity": Decimal(2)}),
            )


@pytest.mark.asyncio
async def test_draft_edit_lifecycle_replay_and_archived_selection_fail_closed(
    price_book_fixture,
):
    factory, context, branch = price_book_fixture
    service, item, version, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        catalog = await service.catalog(session, context=context)
    tax_id = catalog.tax_classifications[0].id
    async with factory() as session:
        edited = await service.update_draft(
            session,
            context=context,
            version_id=version.id,
            payload=PriceVersionUpdate(
                expected_version=1,
                tax_classification_id=tax_id,
                currency="USD",
                unit_price=Decimal("154.25"),
                effective_at=effective,
                components=(
                    ComponentCreate(
                        component_type="labor",
                        label="Corrected labor",
                        quantity=Decimal(2),
                        unit_cost=Decimal(40),
                    ),
                ),
            ),
        )
    assert edited.version == 2
    async with factory() as session:
        active = await service.activate(
            session,
            context=context,
            version_id=version.id,
            expected_version=2,
            reason="Approved",
        )
    async with factory() as session:
        replay = await service.activate(
            session,
            context=context,
            version_id=version.id,
            expected_version=2,
            reason="Approved",
        )
    assert replay.id == active.id and replay.version == active.version
    async with factory() as session:
        inactive = await service.transition_lifecycle(
            session,
            context=context,
            version_id=version.id,
            target_status="inactive",
            expected_version=active.version,
            reason="Seasonal pause",
        )
    async with factory() as session:
        archived = await service.transition_lifecycle(
            session,
            context=context,
            version_id=version.id,
            target_status="archived",
            expected_version=inactive.version,
            reason="Retired",
        )
    assert archived.status == "archived"
    async with factory() as session:
        with pytest.raises((PriceBookConflict, PriceBookNotFound)):
            await service.snapshot(
                session,
                context=context,
                item_id=item.id,
                payload=SnapshotRequest(
                    branch_id=branch.id,
                    quantity=Decimal(1),
                    currency="USD",
                    effective_at=effective + timedelta(minutes=1),
                    idempotency_key="archived-price-001",
                ),
            )


@pytest.mark.asyncio
async def test_historical_superseded_resolution_and_option_snapshot_evidence(
    price_book_fixture,
):
    factory, context, branch = price_book_fixture
    service, item, first, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        group = await service.create_option_group(
            session,
            context=context,
            payload=OptionGroupCreate(code="LEVEL", name="Service level"),
        )
    async with factory() as session:
        option = await service.add_option(
            session,
            context=context,
            group_id=group.id,
            payload=OptionCreate(service_item_id=item.id, label="Standard", position=1),
        )
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=first.id,
            expected_version=1,
            reason="Initial",
        )
    async with factory() as session:
        tax_id = (
            (await service.catalog(session, context=context)).tax_classifications[0].id
        )
    successor_at = effective + timedelta(days=1)
    async with factory() as session:
        successor = await service.create_version(
            session,
            context=context,
            item_id=item.id,
            payload=PriceVersionCreate(
                tax_classification_id=tax_id,
                currency="USD",
                unit_price=Decimal(175),
                effective_at=successor_at,
            ),
        )
    async with factory() as session:
        await service.activate(
            session,
            context=context,
            version_id=successor.id,
            expected_version=1,
            reason="Successor",
        )
    async with factory() as session:
        historical = await service.snapshot(
            session,
            context=context,
            item_id=item.id,
            payload=SnapshotRequest(
                branch_id=branch.id,
                quantity=Decimal(1),
                currency="USD",
                effective_at=effective + timedelta(hours=1),
                idempotency_key="historical-option-001",
                option_group_id=group.id,
                option_id=option.id,
                historical=True,
            ),
        )
    assert historical.price_version_id == first.id
    assert historical.snapshot_data["option_group_id"] == str(group.id)
    assert historical.snapshot_data["option_id"] == str(option.id)
    async with factory() as session:
        current = await service.snapshot(
            session,
            context=context,
            item_id=item.id,
            payload=SnapshotRequest(
                branch_id=branch.id,
                quantity=Decimal(1),
                currency="USD",
                effective_at=successor_at + timedelta(minutes=1),
                idempotency_key="current-successor-001",
            ),
        )
    assert current.price_version_id == successor.id


def context_with_permissions(
    context: AuthorizationContext, codes: frozenset[str]
) -> AuthorizationContext:
    now = datetime.now(timezone.utc)
    permissions = tuple(
        Permission(
            code=code,
            name=code,
            resource="price_book",
            action=code.rsplit("_", 1)[-1].lower(),
            status="active",
            created_at=now,
            updated_at=now,
        )
        for code in sorted(codes)
    )
    return AuthorizationContext(
        user=context.user,
        company=context.company,
        membership=context.membership,
        authorized_branches=context.authorized_branches,
        active_branch=context.active_branch,
        effective_roles=(),
        effective_permissions=permissions,
        credential_version=context.credential_version,
        authorization_version=context.authorization_version,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("codes", "read_allowed", "manage_allowed", "activate_allowed"),
    [
        (frozenset(), False, False, False),
        (frozenset({PriceBookPermission.READ}), True, False, False),
        (frozenset({PriceBookPermission.MANAGE}), False, True, False),
        (frozenset({PriceBookPermission.ACTIVATE}), False, False, True),
        (
            frozenset({PriceBookPermission.READ, PriceBookPermission.MANAGE}),
            True,
            True,
            False,
        ),
        (
            frozenset({PriceBookPermission.READ, PriceBookPermission.ACTIVATE}),
            True,
            False,
            True,
        ),
        (frozenset(PriceBookPermission.ALL), True, True, True),
    ],
)
async def test_complete_authorization_matrix(
    price_book_fixture,
    codes,
    read_allowed,
    manage_allowed,
    activate_allowed,
):
    factory, base_context, _ = price_book_fixture
    assert base_context.active_branch is not None
    context = context_with_permissions(base_context, codes)
    application = FastAPI()
    application.include_router(price_book_router)

    async def session_override():
        async with factory() as session:
            yield session

    async def context_override():
        return context

    application.dependency_overrides[get_database_session] = session_override
    application.dependency_overrides[get_authorization_context] = context_override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        read = await client.get("/api/v1/price-book")
        manage = await client.post(
            "/api/v1/price-book/categories",
            json={"code": f"AUTH-{uuid4().hex[:8]}", "name": "Authorized"},
        )
        activate = await client.post(
            f"/api/v1/price-book/versions/{uuid4()}/activate",
            json={"expected_version": 1, "reason": "Authorization matrix"},
        )
        snapshot = await client.post(
            f"/api/v1/price-book/service-items/{uuid4()}/snapshots",
            json={
                "branch_id": str(base_context.active_branch.id),
                "quantity": "1",
                "currency": "USD",
                "effective_at": datetime.now(timezone.utc).isoformat(),
                "idempotency_key": f"matrix-{uuid4().hex}",
            },
        )
    assert (read.status_code == 200) is read_allowed
    assert (manage.status_code == 201) is manage_allowed
    assert (activate.status_code != 403) is activate_allowed
    assert (snapshot.status_code != 403) is manage_allowed


@pytest.mark.asyncio
async def test_competing_activation_and_snapshot_during_successor_activation(
    concurrent_price_book_fixture,
):
    factory, context, branch = concurrent_price_book_fixture
    service, item, first, effective = await seed_draft(factory, context, branch)
    async with factory() as session:
        with pytest.raises(PriceBookConflict):
            await service.create_category(
                session,
                context=context,
                payload=CategoryCreate(code="DRAIN", name="Duplicate Drain"),
            )
    async with factory() as session:
        with pytest.raises(PriceBookConflict):
            await service.create_item(
                session,
                context=context,
                payload=ServiceItemCreate(
                    category_id=item.category_id,
                    code=item.code,
                    name="Duplicate item",
                    customer_description="Must be rejected.",
                ),
            )
    async with factory() as session:
        tax_id = (
            (await service.catalog(session, context=context)).tax_classifications[0].id
        )
    async with factory() as session:
        competing = await service.create_version(
            session,
            context=context,
            item_id=item.id,
            payload=PriceVersionCreate(
                tax_classification_id=tax_id,
                currency="USD",
                unit_price=Decimal(160),
                effective_at=effective,
            ),
        )

    async def activate(version_id):
        async with factory() as session:
            return await service.activate(
                session,
                context=context,
                version_id=version_id,
                expected_version=1,
                reason=f"Competing {version_id}",
            )

    results = await asyncio.gather(
        activate(first.id), activate(competing.id), return_exceptions=True
    )
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, PriceBookConflict) for result in results) == 1

    loser_id = competing.id if isinstance(results[1], Exception) else first.id
    async with factory() as session:
        with pytest.raises(PriceBookConflict):
            await service.update_draft(
                session,
                context=context,
                version_id=loser_id,
                payload=PriceVersionUpdate(
                    expected_version=99,
                    tax_classification_id=tax_id,
                    currency="USD",
                    unit_price=Decimal(170),
                    effective_at=effective,
                ),
            )

    active = next(result for result in results if not isinstance(result, Exception))
    successor_at = effective + timedelta(days=1)
    async with factory() as session:
        successor = await service.create_version(
            session,
            context=context,
            item_id=item.id,
            payload=PriceVersionCreate(
                tax_classification_id=tax_id,
                currency="USD",
                unit_price=Decimal(180),
                effective_at=successor_at,
            ),
        )

    async def activate_successor():
        async with factory() as session:
            return await service.activate(
                session,
                context=context,
                version_id=successor.id,
                expected_version=1,
                reason="Successor",
            )

    async def resolve_historical():
        async with factory() as session:
            return await service.snapshot(
                session,
                context=context,
                item_id=item.id,
                payload=SnapshotRequest(
                    branch_id=branch.id,
                    quantity=Decimal(1),
                    currency="USD",
                    effective_at=effective + timedelta(hours=1),
                    idempotency_key="concurrent-history-001",
                    historical=True,
                ),
            )

    _, snapshot = await asyncio.gather(activate_successor(), resolve_historical())
    assert snapshot.price_version_id == active.id
