from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership
from app.platform.users.identity_models import PendingEmailChange
from app.platform.users.models import User, UserCredential


EMAIL_LOCK_NAMESPACE = 7_321_941


class IdentityRepositoryError(Exception):
    pass


class IdentityRepositoryConflictError(IdentityRepositoryError):
    pass


class IdentityRepositoryNotFoundError(IdentityRepositoryError):
    pass


class UserIdentityRepository:
    """Owns locking and persistence for global identity mutations."""

    @staticmethod
    def require_normalized_email(value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or value != normalized:
            raise ValueError("Email must be normalized before repository use.")
        return normalized

    @staticmethod
    async def lock_normalized_email(
        session: AsyncSession, normalized_email: str
    ) -> None:
        email = UserIdentityRepository.require_normalized_email(normalized_email)
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(email, EMAIL_LOCK_NAMESPACE)
                )
            )
        )

    @staticmethod
    async def get_user_for_identity_update(
        session: AsyncSession, user_id: UUID
    ) -> User | None:
        return await session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
        return await session.scalar(select(User).where(User.id == user_id))

    @staticmethod
    async def get_user_by_normalized_email(
        session: AsyncSession,
        normalized_email: str,
        *,
        for_update: bool = False,
    ) -> User | None:
        email = UserIdentityRepository.require_normalized_email(normalized_email)
        statement = select(User).where(User.normalized_email == email)
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def has_active_company_membership(
        session: AsyncSession,
        *,
        user_id: UUID,
        company_id: UUID,
    ) -> bool:
        return (
            await session.scalar(
                select(Membership.id)
                .where(
                    Membership.user_id == user_id,
                    Membership.company_id == company_id,
                    Membership.status == "active",
                )
                .limit(1)
            )
        ) is not None

    @staticmethod
    async def is_normalized_email_available(
        session: AsyncSession,
        normalized_email: str,
        *,
        now: datetime,
        excluding_user_id: UUID | None = None,
    ) -> bool:
        email = UserIdentityRepository.require_normalized_email(normalized_email)
        user_statement = select(User.id).where(User.normalized_email == email)
        if excluding_user_id is not None:
            user_statement = user_statement.where(User.id != excluding_user_id)
        existing_user = await session.scalar(user_statement.limit(1))
        if existing_user is not None:
            return False
        reservation = await session.scalar(
            select(PendingEmailChange.id)
            .where(
                PendingEmailChange.proposed_normalized_email == email,
                PendingEmailChange.status == "pending",
                PendingEmailChange.expires_at > now,
            )
            .limit(1)
        )
        return reservation is None

    @staticmethod
    async def expire_stale_pending_email_changes(
        session: AsyncSession,
        *,
        now: datetime,
        user_id: UUID | None = None,
        normalized_email: str | None = None,
        initiating_company_id: UUID | None = None,
    ) -> int:
        filters = [
            PendingEmailChange.status == "pending",
            PendingEmailChange.expires_at <= now,
        ]
        if user_id is not None:
            filters.append(PendingEmailChange.user_id == user_id)
        if normalized_email is not None:
            filters.append(
                PendingEmailChange.proposed_normalized_email
                == UserIdentityRepository.require_normalized_email(normalized_email)
            )
        if initiating_company_id is not None:
            filters.append(
                PendingEmailChange.initiating_company_id == initiating_company_id
            )
        result = await session.execute(
            update(PendingEmailChange)
            .where(*filters)
            .values(status="expired", expired_at=now, updated_at=now)
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    @staticmethod
    async def create_pending_email_change(
        session: AsyncSession,
        *,
        user_id: UUID,
        proposed_normalized_email: str,
        proposed_display_email: str | None,
        verification_token_hash: str,
        reason_code: str,
        expires_at: datetime,
        now: datetime,
        initiated_by_user_id: UUID | None = None,
        initiating_company_id: UUID | None = None,
    ) -> PendingEmailChange:
        email = UserIdentityRepository.require_normalized_email(
            proposed_normalized_email
        )
        await UserIdentityRepository.lock_normalized_email(session, email)
        user = await UserIdentityRepository.get_user_for_identity_update(
            session, user_id
        )
        if user is None:
            raise IdentityRepositoryNotFoundError("User identity was not found.")
        await UserIdentityRepository.expire_stale_pending_email_changes(
            session,
            now=now,
            user_id=user_id,
        )
        await UserIdentityRepository.expire_stale_pending_email_changes(
            session,
            now=now,
            normalized_email=email,
        )
        if not await UserIdentityRepository.is_normalized_email_available(
            session,
            email,
            now=now,
        ):
            raise IdentityRepositoryConflictError("Email is unavailable.")
        active_request = await UserIdentityRepository.get_active_pending_email_change(
            session,
            user_id=user_id,
            now=now,
            for_update=True,
        )
        if (
            active_request is not None
            and active_request.initiating_company_id != initiating_company_id
        ):
            raise IdentityRepositoryConflictError(
                "Another identity workflow is already pending."
            )
        await UserIdentityRepository.revoke_active_pending_email_changes(
            session,
            user_id=user_id,
            now=now,
            terminal_status="superseded",
        )
        record = PendingEmailChange(
            user_id=user_id,
            proposed_normalized_email=email,
            proposed_display_email=proposed_display_email,
            verification_token_hash=verification_token_hash,
            status="pending",
            reason_code=reason_code,
            initiated_by_user_id=initiated_by_user_id,
            initiating_company_id=initiating_company_id,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_pending_email_change_for_update(
        session: AsyncSession, verification_token_hash: str
    ) -> PendingEmailChange | None:
        return await session.scalar(
            select(PendingEmailChange)
            .where(
                PendingEmailChange.verification_token_hash == verification_token_hash
            )
            .with_for_update()
        )

    @staticmethod
    async def get_pending_email_change_by_id_for_update(
        session: AsyncSession, change_id: UUID
    ) -> PendingEmailChange | None:
        return await session.scalar(
            select(PendingEmailChange)
            .where(PendingEmailChange.id == change_id)
            .with_for_update()
        )

    @staticmethod
    async def get_active_pending_email_change(
        session: AsyncSession,
        *,
        user_id: UUID,
        now: datetime,
        for_update: bool = False,
        initiating_company_id: UUID | None = None,
    ) -> PendingEmailChange | None:
        statement = select(PendingEmailChange).where(
            PendingEmailChange.user_id == user_id,
            PendingEmailChange.status == "pending",
            PendingEmailChange.expires_at > now,
        )
        if initiating_company_id is not None:
            statement = statement.where(
                PendingEmailChange.initiating_company_id == initiating_company_id
            )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    @staticmethod
    async def revoke_active_pending_email_changes(
        session: AsyncSession,
        *,
        user_id: UUID,
        now: datetime,
        terminal_status: str = "revoked",
    ) -> int:
        if terminal_status not in {"revoked", "superseded"}:
            raise ValueError("Pending email terminal status is invalid.")
        values: dict[str, object] = {
            "status": terminal_status,
            "updated_at": now,
            f"{terminal_status}_at": now,
        }
        result = await session.execute(
            update(PendingEmailChange)
            .where(
                PendingEmailChange.user_id == user_id,
                PendingEmailChange.status == "pending",
            )
            .values(**values)
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    @staticmethod
    def mark_pending_email_change_confirmed(
        record: PendingEmailChange, *, now: datetime
    ) -> None:
        if record.status != "pending" or record.expires_at <= now:
            raise IdentityRepositoryConflictError(
                "Pending email change cannot be confirmed."
            )
        record.status = "confirmed"
        record.confirmed_at = now
        record.updated_at = now

    @staticmethod
    async def apply_verified_email_change(
        session: AsyncSession,
        *,
        user_id: UUID,
        normalized_email: str,
        verified_at: datetime,
    ) -> User:
        email = UserIdentityRepository.require_normalized_email(normalized_email)
        await UserIdentityRepository.lock_normalized_email(session, email)
        user = await UserIdentityRepository.get_user_for_identity_update(
            session, user_id
        )
        if user is None:
            raise IdentityRepositoryNotFoundError("User identity was not found.")
        if not await UserIdentityRepository.is_normalized_email_available(
            session,
            email,
            now=verified_at,
            excluding_user_id=user_id,
        ):
            reservation = await session.scalar(
                select(PendingEmailChange.id).where(
                    PendingEmailChange.user_id == user_id,
                    PendingEmailChange.proposed_normalized_email == email,
                    PendingEmailChange.status == "pending",
                )
            )
            if reservation is None:
                raise IdentityRepositoryConflictError("Email is unavailable.")
        user.normalized_email = email
        user.email_verified_at = verified_at
        user.updated_at = verified_at
        await session.flush()
        return user

    @staticmethod
    async def get_credential_for_update(
        session: AsyncSession, user_id: UUID
    ) -> UserCredential | None:
        return await session.scalar(
            select(UserCredential)
            .where(UserCredential.user_id == user_id)
            .with_for_update()
        )

    @staticmethod
    async def get_credential(
        session: AsyncSession, user_id: UUID
    ) -> UserCredential | None:
        return await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )

    @staticmethod
    def increment_credential_version(
        credential: UserCredential, *, updated_at: datetime
    ) -> None:
        credential.credential_version += 1
        credential.updated_at = updated_at

    @staticmethod
    async def set_forced_password_reset_required(
        session: AsyncSession,
        *,
        user_id: UUID,
        required_at: datetime,
        reason_code: str,
        required_by_user_id: UUID,
        company_id: UUID | None,
    ) -> tuple[UserCredential, bool]:
        credential = await UserIdentityRepository.get_credential_for_update(
            session, user_id
        )
        if credential is None:
            raise IdentityRepositoryNotFoundError("User credential was not found.")
        if (
            credential.password_change_required
            and credential.password_change_required_reason_code == reason_code
            and credential.password_change_required_by_user_id == required_by_user_id
            and credential.password_change_required_company_id == company_id
        ):
            return credential, False
        credential.password_change_required = True
        credential.password_change_required_at = required_at
        credential.password_change_required_reason_code = reason_code
        credential.password_change_required_by_user_id = required_by_user_id
        credential.password_change_required_company_id = company_id
        credential.password_change_required_cleared_at = None
        credential.updated_at = required_at
        await session.flush()
        return credential, True

    @staticmethod
    async def clear_forced_password_reset_required(
        session: AsyncSession,
        *,
        user_id: UUID,
        cleared_at: datetime,
    ) -> tuple[UserCredential, bool]:
        credential = await UserIdentityRepository.get_credential_for_update(
            session, user_id
        )
        if credential is None:
            raise IdentityRepositoryNotFoundError("User credential was not found.")
        if not credential.password_change_required:
            return credential, False
        credential.password_change_required = False
        credential.password_change_required_cleared_at = cleared_at
        credential.updated_at = cleared_at
        await session.flush()
        return credential, True


user_identity_repository = UserIdentityRepository()
