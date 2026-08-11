from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import CustomerNote
from app.events.models import BusinessEvent
from app.platform.permissions.authorization import AuthorizedBranch
from tests.customers.test_api import build_app, seed_customer_fixture


@pytest_asyncio.fixture
async def crm_database():
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_launch_intake_duplicate_note_consent_and_location_workflow(
    crm_database,
) -> None:
    _, factory = crm_database
    fixture = await seed_customer_fixture(factory, "CRMLAUNCH")
    app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        intake_payload = {
            "customer_type": "individual",
            "first_name": "Avery",
            "last_name": "Morgan",
            "business_name": None,
            "primary_phone": "727-555-0199",
            "secondary_phone": None,
            "email": "AVERY@example.com",
            "preferred_contact_method": "email",
            "status": "active",
            "source": "web_referral",
            "is_vip": True,
            "internal_notes": "Requires text before arrival.",
        }
        created = await client.post("/api/v1/customers/intake", json=intake_payload)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["duplicate_warnings"] == []
        customer = body["customer"]
        assert customer["display_name"] == "Avery Morgan"
        assert customer["preferred_contact"]["email"] == "avery@example.com"

        duplicate = await client.post(
            "/api/v1/customers/duplicate-check",
            json={"phone": "(727) 555-0199", "email": "avery@example.com"},
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["matches"][0]["reasons"] == ["phone", "email"]

        location_one = await client.post(
            f"/api/v1/customers/{customer['id']}/locations",
            json={
                "address": "10 First Ave",
                "city": "Clearwater",
                "state": "FL",
                "postal_code": "33755",
                "property_type": "single_family",
                "is_primary": True,
            },
        )
        location_two = await client.post(
            f"/api/v1/customers/{customer['id']}/locations",
            json={
                "address": "20 Second Ave",
                "city": "Clearwater",
                "state": "FL",
                "postal_code": "33756",
                "property_type": "condo",
                "is_primary": True,
            },
        )
        assert location_one.status_code == location_two.status_code == 201
        locations = await client.get(f"/api/v1/customers/{customer['id']}/locations")
        assert sum(item["is_primary"] for item in locations.json()) == 1

        note = await client.post(
            f"/api/v1/customers/{customer['id']}/notes",
            json={"body": "  Customer requested email confirmation.  "},
        )
        assert note.status_code == 201
        assert note.json()["body"] == "Customer requested email confirmation."

        granted = await client.post(
            f"/api/v1/customers/{customer['id']}/consents",
            json={
                "channel": "email",
                "decision": "granted",
                "source": "staff_confirmed",
            },
        )
        withdrawn = await client.post(
            f"/api/v1/customers/{customer['id']}/consents",
            json={
                "channel": "email",
                "decision": "withdrawn",
                "source": "customer_request",
            },
        )
        assert granted.status_code == withdrawn.status_code == 201
        consent_history = await client.get(
            f"/api/v1/customers/{customer['id']}/consents"
        )
        assert [item["decision"] for item in consent_history.json()] == [
            "withdrawn",
            "granted",
        ]
        detail = await client.get(f"/api/v1/customers/{customer['id']}")
        assert detail.json()["note_history"][0]["body"] == note.json()["body"]
        timeline = await client.get(f"/api/v1/customers/{customer['id']}/timeline")
        consent_entries = [
            item
            for item in timeline.json()["items"]
            if item["event_type"] == "customer.consent_recorded"
        ]
        assert consent_entries[0]["summary"] == "EMAIL consent withdrawn"
        assert consent_entries[0]["metadata"]["decision"] == "withdrawn"
        assert "reason" not in consent_entries[0]["metadata"]
        assert all("body" not in item["metadata"] for item in timeline.json()["items"])

    async with factory() as session:
        notes = list(
            (
                await session.scalars(
                    select(CustomerNote).where(
                        CustomerNote.customer_id == UUID(customer["id"])
                    )
                )
            ).all()
        )
        events = list(
            (
                await session.scalars(
                    select(BusinessEvent).where(
                        BusinessEvent.company_id == fixture.context.company.id
                    )
                )
            ).all()
        )
    assert len(notes) == 1
    assert sum(event.event_type == "customer.consent_recorded" for event in events) == 2
    assert all(event.company_id == fixture.context.company.id for event in events)


@pytest.mark.asyncio
async def test_launch_endpoints_hide_other_company_customer(
    crm_database,
) -> None:
    _, factory = crm_database
    fixture = await seed_customer_fixture(factory, "CRMTENANT")
    owned_app = build_app(factory, fixture.context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owned_app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/v1/customers/intake",
            json={
                "customer_type": "business",
                "business_name": "Tenant One",
                "primary_phone": "7275550101",
            },
        )
        customer_id = created.json()["customer"]["id"]

    other_app = build_app(factory, fixture.other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        assert (
            await client.get(f"/api/v1/customers/{customer_id}/consents")
        ).status_code == 404
        assert (
            await client.post(
                f"/api/v1/customers/{customer_id}/notes", json={"body": "hidden"}
            )
        ).status_code == 404
        assert (
            await client.post(
                "/api/v1/customers/duplicate-check", json={"phone": "7275550101"}
            )
        ).json() == {"matches": []}


@pytest.mark.asyncio
async def test_launch_endpoints_reject_cross_company_active_branch(
    crm_database,
) -> None:
    _, factory = crm_database
    fixture = await seed_customer_fixture(factory, "CRMBRANCH")
    now = datetime.now(timezone.utc)
    invalid_context = replace(
        fixture.context,
        active_branch=AuthorizedBranch(
            id=uuid4(),
            company_id=fixture.other_context.company.id,
            name="Other Branch",
            code="OTHER",
            status="active",
            timezone="America/New_York",
            is_primary=False,
            created_at=now,
            updated_at=now,
            archived_at=None,
        ),
    )
    app = build_app(factory, invalid_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/customers/duplicate-check", json={"phone": "7275550101"}
        )
    assert response.status_code == 404
