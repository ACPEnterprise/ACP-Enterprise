"""Dedicated asynchronous consumer for identity/security notification intents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.communications.delivery import TransactionalDeliveryService
from app.communications.postmark import PostmarkIdentityProvider
from app.communications.templates import (
    RenderedTransactionalMessage,
    render_employee_invitation,
)
from app.core.config import Settings, settings
from app.database.session import AsyncSessionFactory
from app.platform.company.models import Company
from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.onboarding.models import (
    IdentityOnboardingInvitation,
    IdentityOnboardingRequest,
)
from app.platform.onboarding.service import IdentityOnboardingService
from app.platform.users.models import User

DELIVERABLE_IDENTITY_TYPES = frozenset({"identity.onboarding_invitation"})


class IdentityInvitationResolver:
    def __init__(self, configuration: Settings) -> None:
        self.configuration = configuration

    async def render(self, record: NotificationOutbox) -> RenderedTransactionalMessage:
        if record.notification_type != "identity.onboarding_invitation":
            raise ValueError("Identity template is not supported by this consumer.")
        invitation_id = UUID(str(record.payload.get("invitation_id", "")))
        async with AsyncSessionFactory() as session:
            delivery = await IdentityOnboardingService(self.configuration).claim_protected_delivery(
                session, invitation_id=invitation_id
            )
        async with AsyncSessionFactory() as session:
            row = (
                await session.execute(
                    select(User.display_name, Company.name, IdentityOnboardingInvitation.expires_at)
                    .join(IdentityOnboardingRequest, IdentityOnboardingRequest.user_id == User.id)
                    .join(IdentityOnboardingInvitation, IdentityOnboardingInvitation.onboarding_request_id == IdentityOnboardingRequest.id)
                    .join(Company, Company.id == IdentityOnboardingRequest.company_id)
                    .where(IdentityOnboardingInvitation.id == invitation_id)
                )
            ).one()
        origin = self.configuration.identity_email_activation_origin.rstrip("/")
        return render_employee_invitation(
            recipient_display_name=row.display_name,
            company_display_name=row.name,
            activation_url=f"{origin}/activate?token={delivery.secret}",
            expected_origin=origin,
            expiration_copy=f"This invitation expires {row.expires_at.isoformat()}.",
        )


class IdentityOutboxWorker:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self.provider = PostmarkIdentityProvider(
            token_file=configuration.identity_email_postmark_token_file or "",
            sender=configuration.identity_email_sender or "",
        )
        self.resolver = IdentityInvitationResolver(configuration)
        self.delivery = TransactionalDeliveryService()

    async def run_once(self) -> int:
        now = datetime.now(timezone.utc)
        async with AsyncSessionFactory() as session, session.begin():
            await NotificationOutboxRepository.release_abandoned_claims(
                session,
                claimed_before=now - timedelta(minutes=5),
                release_at=now,
                notification_types=DELIVERABLE_IDENTITY_TYPES,
            )
            records = await NotificationOutboxRepository.claim_batch(
                session,
                worker_id="identity-postmark-preview",
                now=now,
                limit=10,
                notification_types=DELIVERABLE_IDENTITY_TYPES,
            )
            record_ids = tuple(record.id for record in records)
        for record_id in record_ids:
            async with AsyncSessionFactory() as session, session.begin():
                record = await session.get(NotificationOutbox, record_id)
                if record is None or record.status != "claimed":
                    continue
                result = await self.delivery.deliver_claimed(
                    session,
                    record=record,
                    provider=self.provider,
                    resolver=self.resolver,
                    now=datetime.now(timezone.utc),
                )
            if result.outcome in {"accepted", "delivered"}:
                invitation_id = UUID(str(record.payload["invitation_id"]))
                async with AsyncSessionFactory() as session:
                    await IdentityOnboardingService(self.configuration).complete_protected_delivery(
                        session, invitation_id=invitation_id
                    )
        return len(record_ids)

    async def run(self) -> None:
        if not self.configuration.identity_outbox_worker_enabled:
            raise RuntimeError("Identity delivery worker is disabled.")
        await self.provider.verify_authentication()
        while True:
            processed = await self.run_once()
            if processed == 0:
                await asyncio.sleep(self.configuration.identity_outbox_worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(IdentityOutboxWorker().run())
