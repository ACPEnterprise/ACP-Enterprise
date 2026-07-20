import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.customers.models import Customer, CustomerContact
from app.customers.router import router as customer_router
from app.customers.schemas import CustomerCreate
from app.customers.service import customer_service
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True)
class CustomerFixture:
    context: AuthorizationContext
    restricted_context: AuthorizationContext
    other_context: AuthorizationContext


@pytest_asyncio.fixture
async def customer_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_customer_fixture(
    factory: async_sessionmaker[AsyncSession], prefix: str
) -> CustomerFixture:
    suffix = uuid4().hex[:8]
    async with factory() as session, session.begin():
        user = User(
            normalized_email=f"{prefix.lower()}-{suffix}@example.com",
            first_name="Customer",
            last_name="Manager",
            display_name="Customer Manager",
            status="active",
        )
        session.add(user)
        await session.flush()
        session.add(
            UserCredential(
                user_id=user.id,
                password_hash="$argon2id$customer-domain-test",
            )
        )
        company = Company(
            name=f"{prefix} Company",
            code=f"{prefix}{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        other_company = Company(
            name=f"{prefix} Other Company",
            code=f"{prefix}O{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([company, other_company])
        await session.flush()
        membership = Membership(
            user_id=user.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=False,
        )
        other_membership = Membership(
            user_id=user.id,
            company_id=other_company.id,
            status="active",
            has_all_branch_access=False,
        )
        session.add_all([membership, other_membership])
        permissions: list[Permission] = []
        for code in sorted(CustomerPermission.ALL):
            permission = await session.scalar(
                select(Permission).where(Permission.code == code)
            )
            if permission is None:
                permission = Permission(
                    code=code,
                    name=code.replace("_", " ").title(),
                    resource="customer",
                    action=code.rsplit("_", 1)[-1].lower(),
                    status="active",
                )
                session.add(permission)
                await session.flush()
            permissions.append(permission)

    context = AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=tuple(permissions),
        credential_version=1,
        authorization_version=1,
    )
    restricted = AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )
    other = AuthorizationContext(
        user=user,
        company=other_company,
        membership=other_membership,
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=tuple(permissions),
        credential_version=1,
        authorization_version=1,
    )
    return CustomerFixture(context, restricted, other)


def build_app(
    factory: async_sessionmaker[AsyncSession], context: AuthorizationContext
) -> FastAPI:
    app = FastAPI()
    app.include_router(customer_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def context_override() -> AuthorizationContext:
        return context

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_authorization_context] = context_override
    return app


@pytest.mark.asyncio
async def test_customer_api_tenant_workflow_events_and_validation(
    customer_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = customer_database
    fixture = await seed_customer_fixture(factory, "CUSTA")
    app = build_app(factory, fixture.context)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/customers",
            json={
                "customer_type": "residential",
                "display_name": "Jordan Rivera",
                "preferred_contact_method": "phone",
                "marketing_source": "referral",
                "tax_exempt": False,
                "status": "prospect",
            },
        )
        assert first.status_code == 201, first.text
        customer = first.json()
        assert customer["customer_number"] == "CUS-000001"
        assert customer["company_id"] == str(fixture.context.company.id)

        second = await client.post(
            "/api/v1/customers",
            json={
                "customer_type": "commercial",
                "display_name": "Rivera Holdings",
                "legal_name": "Rivera Holdings LLC",
            },
        )
        assert second.status_code == 201
        assert second.json()["customer_number"] == "CUS-000002"

        first_contact = await client.post(
            f"/api/v1/customers/{customer['id']}/contacts",
            json={
                "first_name": "Jordan",
                "last_name": "Rivera",
                "email": "jordan@example.com",
                "mobile_phone": "7275550100",
                "is_preferred": True,
            },
        )
        assert first_contact.status_code == 201, first_contact.text
        second_contact = await client.post(
            f"/api/v1/customers/{customer['id']}/contacts",
            json={
                "first_name": "Taylor",
                "last_name": "Rivera",
                "office_phone": "7275550101",
                "is_preferred": True,
            },
        )
        assert second_contact.status_code == 201, second_contact.text
        contacts = await client.get(f"/api/v1/customers/{customer['id']}/contacts")
        assert sum(record["is_preferred"] for record in contacts.json()) == 1
        deactivated = await client.patch(
            f"/api/v1/customers/{customer['id']}/contacts/{second_contact.json()['id']}",
            json={"active": False},
        )
        assert deactivated.status_code == 200
        assert not deactivated.json()["active"]

        location = await client.post(
            f"/api/v1/customers/{customer['id']}/locations",
            json={
                "nickname": "Home",
                "address": "123 Main Street",
                "city": "Clearwater",
                "state": "Florida",
                "postal_code": "33755",
                "gate_code": "Call on arrival",
            },
        )
        assert location.status_code == 201, location.text
        location_update = await client.patch(
            f"/api/v1/customers/{customer['id']}/locations/{location.json()['id']}",
            json={"active": False},
        )
        assert location_update.status_code == 200
        assert not location_update.json()["active"]

        status_response = await client.patch(
            f"/api/v1/customers/{customer['id']}/status",
            json={"status": "active"},
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "active"
        unchanged = await client.patch(f"/api/v1/customers/{customer['id']}", json={})
        assert unchanged.status_code == 200
        invalid = await client.patch(
            f"/api/v1/customers/{customer['id']}",
            json={"customer_number": "CUS-999999"},
        )
        assert invalid.status_code == 422

    async with factory() as session:
        stored_contacts = list(
            (
                await session.scalars(
                    select(CustomerContact).where(
                        CustomerContact.customer_id == UUID(customer["id"])
                    )
                )
            ).all()
        )
        assert sum(record.is_preferred for record in stored_contacts) == 0
        events = {
            event_type
            for event_type in (
                await session.scalars(
                    select(BusinessEvent.event_type).where(
                        BusinessEvent.company_id == fixture.context.company.id
                    )
                )
            ).all()
        }
    assert {
        "customer.created",
        "customer.status_changed",
        "contact.created",
        "contact.deactivated",
        "service_location.created",
        "service_location.deactivated",
    }.issubset(events)


@pytest.mark.asyncio
async def test_customer_authorization_cross_tenant_and_concurrent_numbering(
    customer_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
) -> None:
    _, factory = customer_database
    fixture = await seed_customer_fixture(factory, "CUSTB")
    async with factory() as session:
        owned = await customer_service.create_customer(
            session,
            context=fixture.context,
            data=CustomerCreate(
                customer_type="hoa",  # type: ignore[arg-type]
                display_name="Bayview HOA",
            ),
        )

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/customers/{owned.id}")
    assert response.status_code == 404

    restricted_app = build_app(factory, fixture.restricted_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restricted_app), base_url="http://test"
    ) as client:
        denied = await client.get("/api/v1/customers")
    assert denied.status_code == 403

    async def create_concurrently(name: str) -> str:
        async with factory() as session:
            record = await customer_service.create_customer(
                session,
                context=fixture.context,
                data=CustomerCreate(
                    customer_type="commercial",  # type: ignore[arg-type]
                    display_name=name,
                ),
            )
            return record.customer_number

    numbers = await asyncio.gather(
        create_concurrently("Concurrent One"),
        create_concurrently("Concurrent Two"),
    )
    assert len(set(numbers)) == 2
    assert sorted(numbers) == ["CUS-000002", "CUS-000003"]

    async with factory() as session:
        other_numbers = list(
            (
                await session.scalars(
                    select(Customer.customer_number).where(
                        Customer.company_id == fixture.other_context.company.id
                    )
                )
            ).all()
        )
    assert other_numbers == []
