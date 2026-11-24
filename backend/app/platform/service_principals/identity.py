"""Safe discovery of existing service-principal identities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership
from app.platform.users.models import User, UserCredential


@dataclass(frozen=True, slots=True)
class ExistingServiceIdentity:
    user: User
    credential: UserCredential
    membership: Membership


async def find_existing_service_identity(
    session: AsyncSession,
    *,
    normalized_email: str,
    company_id: UUID,
) -> ExistingServiceIdentity | None:
    """Find a reserved service identity without adopting an unrelated user.

    ``users`` is shared, while membership visibility is tenant-scoped.  The
    caller must establish the canonical company RLS context before invoking
    this function.  An existing deterministic email is never replaced or
    duplicated; it must have one active membership in the intended company
    and a usable credential.
    """

    user = await session.scalar(
        select(User).where(User.normalized_email == normalized_email).with_for_update()
    )
    if user is None:
        return None
    if user.status != "active":
        raise ValueError("Existing service identity is not active.")

    credential = await session.scalar(
        select(UserCredential)
        .where(UserCredential.user_id == user.id)
        .with_for_update()
    )
    if credential is None:
        raise ValueError("Existing service identity credential is missing.")

    memberships = (
        await session.scalars(
            select(Membership).where(Membership.user_id == user.id).with_for_update()
        )
    ).all()
    active_memberships = [item for item in memberships if item.status == "active"]
    target_memberships = [
        item for item in active_memberships if item.company_id == company_id
    ]
    if len(target_memberships) != 1:
        raise ValueError(
            "Existing service identity lacks exactly one active intended-company membership."
        )
    if any(item.company_id != company_id for item in active_memberships):
        raise ValueError(
            "Existing service identity is already active in another company."
        )

    return ExistingServiceIdentity(user, credential, target_memberships[0])
