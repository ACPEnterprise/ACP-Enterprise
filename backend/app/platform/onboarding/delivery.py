"""Provider-neutral protected invitation delivery qualification boundary."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .service import IdentityOnboardingService, OnboardingConflictError


@dataclass(frozen=True)
class DeliveryQualification:
    invitation_id: UUID
    status: str


class ProtectedEnvelopeQualificationDelivery:
    """Non-production lifecycle proof; it intentionally sends no message."""

    def __init__(self, onboarding: IdentityOnboardingService) -> None:
        self.onboarding = onboarding

    async def qualify(
        self, session: AsyncSession, *, invitation_id: UUID
    ) -> DeliveryQualification:
        if self.onboarding.configuration.environment not in {"test", "development"}:
            raise OnboardingConflictError(
                "Protected delivery qualification is unavailable."
            )
        delivery = await self.onboarding.claim_protected_delivery(
            session, invitation_id=invitation_id
        )
        if not delivery.secret:
            raise OnboardingConflictError(
                "Protected delivery qualification is unavailable."
            )
        await self.onboarding.complete_protected_delivery(
            session, invitation_id=invitation_id
        )
        return DeliveryQualification(
            invitation_id=invitation_id,
            status="qualified_without_external_delivery",
        )
