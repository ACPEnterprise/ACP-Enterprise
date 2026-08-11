from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.communications.contracts import CommunicationRequest
from app.communications.service import communication_service
from app.communications.types import CommunicationChannel, CommunicationType
from app.core.config import settings
from app.customers.models import Customer, CustomerContact
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User


@pytest.mark.asyncio
async def test_persisted_request_replay_and_scoped_history() -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        company = Company(
            name="Communications Test",
            code=f"CM{uuid4().hex[:8].upper()}",
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
            normalized_email=f"comms-{uuid4().hex}@example.test",
            first_name="Launch",
            last_name="Operator",
            display_name="Launch Operator",
            status="active",
        )
        customer = Customer(
            company=company,
            customer_number=f"CUS-{uuid4().int % 900000 + 100000}",
            status="active",
            customer_type="residential",
            display_name="Communications Customer",
            normalized_name="communications customer",
            preferred_contact_method="sms",
        )
        contact = CustomerContact(
            customer=customer,
            first_name="Customer",
            last_name="Contact",
            mobile_phone="555-555-0123",
            normalized_mobile_phone="+15555550123",
            active=True,
        )
        session.add_all([company, branch, actor, customer, contact])
        await session.flush()
        source = BusinessEvent(
            event_type="appointment.booked",
            entity_type="appointment",
            entity_id=uuid4(),
            company_id=company.id,
            branch_id=branch.id,
            user_id=actor.id,
            payload={"customer_id": str(customer.id)},
        )
        consent = BusinessEvent(
            event_type="customer.consent_recorded",
            entity_type="customer",
            entity_id=customer.id,
            company_id=company.id,
            branch_id=branch.id,
            user_id=actor.id,
            payload={"customer_id": str(customer.id), "channel": "sms", "decision": "granted"},
        )
        session.add_all([source, consent])
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
    request = CommunicationRequest(
        communication_type=CommunicationType.APPOINTMENT_CONFIRMATION,
        channel=CommunicationChannel.SMS,
        customer_id=customer.id,
        contact_id=contact.id,
        branch_id=branch.id,
        source_event_id=source.id,
        request_key="appointment-confirmation",
        scheduled_at=now,
    )
    try:
        async with factory() as session:
            first = await communication_service.request(
                session, context=context, request=request
            )
        async with factory() as session:
            replay = await communication_service.request(
                session, context=context, request=request
            )
        assert replay.id == first.id

        async with factory() as session:
            history = await communication_service.list(
                session, context=context, branch_id=branch.id, limit=20
            )
            count = await session.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.idempotency_key == first.request_identity)
            )
            requested_events = await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == company.id,
                    BusinessEvent.event_type == "communication.requested",
                )
            )
        assert [item.id for item in history] == [first.id]
        assert count == 1
        assert requested_events == 1
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(NotificationOutbox).where(
                    NotificationOutbox.payload["company_id"].astext == str(company.id)
                )
            )
            await session.execute(
                delete(BusinessEvent).where(BusinessEvent.company_id == company.id)
            )
            await session.delete(contact)
            await session.delete(customer)
            await session.delete(branch)
            await session.delete(actor)
            await session.delete(company)
        await engine.dispose()
