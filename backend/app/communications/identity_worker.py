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
    render_password_reset,
)
from app.core.config import Settings, settings
from app.database.session import AsyncSessionFactory
from app.platform.auth.recovery_delivery import (
    EmployeeRecoveryDeliveryService,
    RecoveryDeliveryError,
)
from app.platform.company.models import Company
from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.onboarding.models import (
    IdentityOnboardingInvitation,
    IdentityOnboardingRequest,
)
from app.platform.onboarding.service import (
    IdentityOnboardingService,
    OnboardingConflictError,
)
from app.platform.users.models import User

DELIVERABLE_IDENTITY_TYPES = frozenset(
    {"identity.onboarding_invitation", "identity.password_reset"}
)


class IdentityInvitationResolver:
    def __init__(self, configuration: Settings) -> None:
        self.configuration = configuration

    async def render(self, record: NotificationOutbox) -> RenderedTransactionalMessage:
        if record.notification_type == "identity.password_reset":
            token_id = UUID(str(record.payload.get("password_reset_token_id", "")))
            async with AsyncSessionFactory() as session:
                recovery = await EmployeeRecoveryDeliveryService(
                    self.configuration
                ).claim(session, token_id=token_id)
            origin = self.configuration.identity_email_activation_origin.rstrip("/")
            return render_password_reset(
                recipient_display_name=recovery.display_name,
                company_display_name=recovery.company_name,
                reset_url=f"{origin}/reset-password?token={recovery.secret}",
                expected_origin=origin,
                expiration_copy=f"This password reset expires {recovery.expires_at.isoformat()}.",
            )
        if record.notification_type != "identity.onboarding_invitation":
            raise ValueError("Identity template is not supported by this consumer.")
        invitation_id = UUID(str(record.payload.get("invitation_id", "")))
        async with AsyncSessionFactory() as session:
            delivery = await IdentityOnboardingService(
                self.configuration
            ).claim_protected_delivery(session, invitation_id=invitation_id)
        async with AsyncSessionFactory() as session:
            row = (
                await session.execute(
                    select(
                        User.display_name,
                        Company.name,
                        IdentityOnboardingInvitation.expires_at,
                    )
                    .join(
                        IdentityOnboardingRequest,
                        IdentityOnboardingRequest.user_id == User.id,
                    )
                    .join(
                        IdentityOnboardingInvitation,
                        IdentityOnboardingInvitation.onboarding_request_id
                        == IdentityOnboardingRequest.id,
                    )
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
            await NotificationOutboxRepository.recover_misclassified_definitive_rejections(
                session,
                recovered_at=now,
                notification_types=DELIVERABLE_IDENTITY_TYPES,
            )
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
                try:
                    result = await self.delivery.deliver_claimed(
                        session,
                        record=record,
                        provider=self.provider,
                        resolver=self.resolver,
                        now=datetime.now(timezone.utc),
                    )
                except (OnboardingConflictError, RecoveryDeliveryError, ValueError):
                    if record.claim_token is None:
                        raise RuntimeError(
                            "Claimed identity notification lost its token."
                        )
                    await NotificationOutboxRepository.mark_failed(
                        session,
                        notification_id=record.id,
                        claim_token=record.claim_token,
                        error_code="identity_delivery_authority_unavailable",
                        error_category="permanent",
                        failed_at=datetime.now(timezone.utc),
                    )
                    continue
            if result.outcome in {"accepted", "delivered"}:
                if record.notification_type == "identity.password_reset":
                    token_id = UUID(str(record.payload["password_reset_token_id"]))
                    async with AsyncSessionFactory() as session:
                        await EmployeeRecoveryDeliveryService(
                            self.configuration
                        ).complete(session, token_id=token_id)
                else:
                    invitation_id = UUID(str(record.payload["invitation_id"]))
                    async with AsyncSessionFactory() as session:
                        await IdentityOnboardingService(
                            self.configuration
                        ).complete_protected_delivery(
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
                await asyncio.sleep(
                    self.configuration.identity_outbox_worker_poll_seconds
                )


if __name__ == "__main__":
    asyncio.run(IdentityOutboxWorker().run())
