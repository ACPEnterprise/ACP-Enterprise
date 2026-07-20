from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.platform.auth.access_tokens import AccessTokenClaims, AccessTokenService
from app.platform.auth.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    RefreshTokenReuseError,
    SessionInvalidError,
)
from app.platform.auth.models import (
    AuthenticationSecurityEvent,
    AuthenticationSession,
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
)
from app.platform.auth.passwords import PasswordService
from app.platform.auth.tokens import SecurityTokenService
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.users.models import User, UserCredential


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class AuthenticationResult:
    user: User
    session_id: UUID
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    session_absolute_expires_at: datetime
    session_idle_expires_at: datetime


@dataclass(frozen=True)
class RefreshResult:
    user: User
    session_id: UUID
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedContext:
    user: User
    authentication_session: AuthenticationSession
    claims: AccessTokenClaims


@dataclass(frozen=True)
class TokenDelivery:
    plaintext_token: str | None


class CredentialService:
    def __init__(
        self,
        password_service: PasswordService,
        configuration: Settings = settings,
    ) -> None:
        self.password_service = password_service
        self.configuration = configuration

    async def set_initial_password(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        password: str,
    ) -> UserCredential:
        encoded_hash = self.password_service.hash_password(password)
        now = utc_now()
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None:
                raise InvalidCredentialsError("Credential operation failed.")
            existing = await session.scalar(
                select(UserCredential)
                .where(UserCredential.user_id == user_id)
                .with_for_update()
            )
            if existing is not None:
                raise InvalidCredentialsError("Credential operation failed.")
            credential = UserCredential(
                user_id=user_id,
                password_hash=encoded_hash,
                password_changed_at=now,
                failed_login_count=0,
                credential_version=1,
            )
            session.add(credential)
        return credential

    async def change_password(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        current_password: str,
        new_password: str,
    ) -> None:
        new_hash = self.password_service.hash_password(new_password)
        now = utc_now()
        async with session.begin():
            credential = await session.scalar(
                select(UserCredential)
                .where(UserCredential.user_id == user_id)
                .with_for_update()
            )
            if credential is None or not self.password_service.verify_password(
                credential.password_hash, current_password
            ):
                raise InvalidCredentialsError("Credential operation failed.")
            self._apply_password_hash(credential, new_hash, now)
            await AuthenticationService.revoke_user_sessions(
                session,
                user_id=user_id,
                reason="credential_changed",
                now=now,
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="authentication.password_change",
                    resource_type="user",
                    resource_id=user_id,
                    actor_user_id=user_id,
                ),
            )

    def _apply_password_hash(
        self,
        credential: UserCredential,
        encoded_hash: str,
        now: datetime,
    ) -> None:
        credential.password_hash = encoded_hash
        credential.password_changed_at = now
        credential.credential_version += 1
        credential.failed_login_count = 0
        credential.last_failed_login_at = None
        credential.locked_until = None
        credential.updated_at = now

    def is_usable(self, credential: UserCredential, now: datetime) -> bool:
        return credential.locked_until is None or credential.locked_until <= now


class AuthenticationService:
    def __init__(
        self,
        password_service: PasswordService,
        token_service: SecurityTokenService,
        access_token_service: AccessTokenService,
        configuration: Settings = settings,
    ) -> None:
        self.password_service = password_service
        self.token_service = token_service
        self.access_token_service = access_token_service
        self.configuration = configuration

    @staticmethod
    def stage_security_event(
        session: AsyncSession,
        *,
        event_type: str,
        success: bool,
        user_id: UUID | None = None,
        normalized_email: str | None = None,
        failure_reason: str | None = None,
        authentication_session_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        session.add(
            AuthenticationSecurityEvent(
                user_id=user_id,
                normalized_attempted_email=normalized_email,
                event_type=event_type,
                success=success,
                failure_reason=failure_reason,
                session_id=authentication_session_id,
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=occurred_at or utc_now(),
            )
        )
        action_map = {
            "login_succeeded": "authentication.login",
            "login_failed": "authentication.login",
            "account_locked": "authentication.login",
            "password_reset_requested": "authentication.password_reset",
            "password_reset_completed": "authentication.password_reset",
            "refresh_token_reused": "authentication.refresh_replay",
            "session_revoked": "authentication.logout",
            "email_verification_requested": "authentication.email_verification",
            "email_verified": "authentication.email_verification",
        }
        audit_service.stage(
            session,
            AuditEntry(
                action=action_map[event_type],
                resource_type="authentication_session"
                if authentication_session_id
                else "user",
                resource_id=authentication_session_id or user_id,
                actor_user_id=user_id,
                outcome="success" if success else "failure",
                reason_code=failure_reason,
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=occurred_at or utc_now(),
                details={"security_event": event_type},
            ),
        )

    async def authenticate(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_label: str | None = None,
    ) -> AuthenticationResult:
        normalized_email = normalize_email(email)
        now = utc_now()
        public_failure = False
        result: AuthenticationResult | None = None

        async with session.begin():
            user = await session.scalar(
                select(User)
                .where(User.normalized_email == normalized_email)
                .with_for_update()
            )
            if user is None:
                self.password_service.perform_dummy_verification(password)
                self.stage_security_event(
                    session,
                    event_type="login_failed",
                    success=False,
                    normalized_email=normalized_email,
                    failure_reason="invalid_credentials",
                    ip_address=ip_address,
                    user_agent=user_agent,
                    occurred_at=now,
                )
                public_failure = True
            else:
                credential = await session.scalar(
                    select(UserCredential)
                    .where(UserCredential.user_id == user.id)
                    .with_for_update()
                )
                failure_reason: str | None = None
                if user.status != "active" or user.archived_at is not None:
                    failure_reason = "user_ineligible"
                elif credential is None:
                    self.password_service.perform_dummy_verification(password)
                    failure_reason = "invalid_credentials"
                elif (
                    credential.locked_until is not None
                    and credential.locked_until > now
                ):
                    failure_reason = "credential_locked"
                elif not self.password_service.verify_password(
                    credential.password_hash, password
                ):
                    credential.failed_login_count += 1
                    credential.last_failed_login_at = now
                    credential.updated_at = now
                    if (
                        credential.failed_login_count
                        >= self.configuration.credential_lockout_threshold
                    ):
                        credential.locked_until = now + timedelta(
                            seconds=self.configuration.credential_lockout_duration_seconds
                        )
                        failure_reason = "credential_locked"
                    else:
                        failure_reason = "invalid_credentials"

                if failure_reason is not None:
                    self.stage_security_event(
                        session,
                        event_type=(
                            "account_locked"
                            if failure_reason == "credential_locked"
                            else "login_failed"
                        ),
                        success=False,
                        user_id=user.id,
                        normalized_email=normalized_email,
                        failure_reason=failure_reason,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        occurred_at=now,
                    )
                    public_failure = True
                else:
                    assert credential is not None
                    credential.failed_login_count = 0
                    credential.last_failed_login_at = None
                    credential.locked_until = None
                    credential.updated_at = now
                    if self.password_service.needs_rehash(credential.password_hash):
                        credential.password_hash = self.password_service.hash_password(
                            password
                        )

                    absolute_expiration = now + timedelta(
                        seconds=self.configuration.session_absolute_lifetime_seconds
                    )
                    idle_expiration = now + timedelta(
                        seconds=self.configuration.session_idle_lifetime_seconds
                    )
                    authentication_session = AuthenticationSession(
                        user_id=user.id,
                        status="active",
                        created_at=now,
                        last_seen_at=now,
                        absolute_expires_at=absolute_expiration,
                        idle_expires_at=idle_expiration,
                        user_agent=user_agent,
                        ip_address=ip_address,
                        device_label=device_label,
                        authentication_method="password",
                        credential_version=credential.credential_version,
                        authorization_version=user.authorization_version,
                    )
                    session.add(authentication_session)
                    await session.flush()

                    plaintext_refresh = self.token_service.generate_token()
                    refresh_expiration = min(
                        now
                        + timedelta(
                            seconds=self.configuration.refresh_token_lifetime_seconds
                        ),
                        absolute_expiration,
                    )
                    session.add(
                        RefreshToken(
                            session_id=authentication_session.id,
                            token_hash=self.token_service.hash_token(plaintext_refresh),
                            family_id=uuid4(),
                            sequence_number=0,
                            issued_at=now,
                            expires_at=refresh_expiration,
                        )
                    )
                    access_token, access_expiration = self.access_token_service.issue(
                        user_id=user.id,
                        session_id=authentication_session.id,
                        credential_version=credential.credential_version,
                        authorization_version=user.authorization_version,
                        now=now,
                    )
                    self.stage_security_event(
                        session,
                        event_type="login_succeeded",
                        success=True,
                        user_id=user.id,
                        normalized_email=normalized_email,
                        authentication_session_id=authentication_session.id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        occurred_at=now,
                    )
                    result = AuthenticationResult(
                        user=user,
                        session_id=authentication_session.id,
                        access_token=access_token,
                        refresh_token=plaintext_refresh,
                        access_token_expires_at=access_expiration,
                        refresh_token_expires_at=refresh_expiration,
                        session_absolute_expires_at=absolute_expiration,
                        session_idle_expires_at=idle_expiration,
                    )

        if public_failure or result is None:
            raise InvalidCredentialsError("Invalid email or password.")
        return result

    async def rotate_refresh_token(
        self,
        session: AsyncSession,
        *,
        plaintext_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RefreshResult:
        token_hash = self.token_service.hash_token(plaintext_token)
        now = utc_now()
        reuse_detected = False
        result: RefreshResult | None = None

        async with session.begin():
            current = await session.scalar(
                select(RefreshToken)
                .where(RefreshToken.token_hash == token_hash)
                .with_for_update()
            )
            if current is None:
                raise InvalidTokenError("Refresh token is invalid.")

            authentication_session = await session.scalar(
                select(AuthenticationSession)
                .where(AuthenticationSession.id == current.session_id)
                .with_for_update()
            )
            if authentication_session is None:
                raise InvalidTokenError("Refresh token is invalid.")

            if current.used_at is not None:
                current.reuse_detected_at = now
                authentication_session.status = "compromised"
                authentication_session.revoked_at = now
                authentication_session.revocation_reason = "refresh_token_reuse"
                await session.execute(
                    update(RefreshToken)
                    .where(
                        RefreshToken.family_id == current.family_id,
                        RefreshToken.revoked_at.is_(None),
                    )
                    .values(
                        revoked_at=now,
                        revocation_reason="refresh_token_reuse",
                    )
                )
                self.stage_security_event(
                    session,
                    event_type="refresh_token_reused",
                    success=False,
                    user_id=authentication_session.user_id,
                    failure_reason="refresh_token_reuse",
                    authentication_session_id=authentication_session.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    occurred_at=now,
                )
                reuse_detected = True
            else:
                if current.revoked_at is not None or current.expires_at <= now:
                    raise InvalidTokenError("Refresh token is invalid.")
                user, credential = await self._validate_session_records(
                    session,
                    authentication_session=authentication_session,
                    now=now,
                    lock=True,
                )
                plaintext_refresh = self.token_service.generate_token()
                refresh_expiration = min(
                    now
                    + timedelta(
                        seconds=self.configuration.refresh_token_lifetime_seconds
                    ),
                    authentication_session.absolute_expires_at,
                )
                replacement = RefreshToken(
                    session_id=authentication_session.id,
                    token_hash=self.token_service.hash_token(plaintext_refresh),
                    family_id=current.family_id,
                    sequence_number=current.sequence_number + 1,
                    issued_at=now,
                    expires_at=refresh_expiration,
                    parent_token_id=current.id,
                )
                session.add(replacement)
                await session.flush()
                current.used_at = now
                current.replaced_by_token_id = replacement.id
                authentication_session.last_seen_at = now
                authentication_session.idle_expires_at = min(
                    now
                    + timedelta(
                        seconds=self.configuration.session_idle_lifetime_seconds
                    ),
                    authentication_session.absolute_expires_at,
                )
                access_token, access_expiration = self.access_token_service.issue(
                    user_id=user.id,
                    session_id=authentication_session.id,
                    credential_version=credential.credential_version,
                    authorization_version=user.authorization_version,
                    now=now,
                )
                result = RefreshResult(
                    user=user,
                    session_id=authentication_session.id,
                    access_token=access_token,
                    refresh_token=plaintext_refresh,
                    access_token_expires_at=access_expiration,
                    refresh_token_expires_at=refresh_expiration,
                )
                audit_service.stage(
                    session,
                    AuditEntry(
                        action="authentication.refresh",
                        resource_type="authentication_session",
                        resource_id=authentication_session.id,
                        actor_user_id=user.id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ),
                )

        if reuse_detected:
            raise RefreshTokenReuseError("Refresh token reuse detected.")
        if result is None:
            raise InvalidTokenError("Refresh token is invalid.")
        return result

    async def validate_access_context(
        self,
        session: AsyncSession,
        claims: AccessTokenClaims,
    ) -> AuthenticatedContext:
        now = utc_now()
        async with session.begin():
            authentication_session = await session.scalar(
                select(AuthenticationSession)
                .where(AuthenticationSession.id == claims.session_id)
                .with_for_update()
            )
            if (
                authentication_session is None
                or authentication_session.user_id != claims.user_id
            ):
                raise SessionInvalidError("Session is invalid.")
            user, credential = await self._validate_session_records(
                session,
                authentication_session=authentication_session,
                now=now,
                lock=False,
            )
            if (
                claims.credential_version != credential.credential_version
                or claims.authorization_version != user.authorization_version
            ):
                raise SessionInvalidError("Session is invalid.")
            if (
                now - authentication_session.last_seen_at
            ).total_seconds() >= self.configuration.session_last_seen_throttle_seconds:
                authentication_session.last_seen_at = now
                authentication_session.idle_expires_at = min(
                    now
                    + timedelta(
                        seconds=self.configuration.session_idle_lifetime_seconds
                    ),
                    authentication_session.absolute_expires_at,
                )
        return AuthenticatedContext(user, authentication_session, claims)

    async def logout(
        self,
        session: AsyncSession,
        *,
        authentication_session_id: UUID,
        actor_user_id: UUID,
        reason: str = "user_logout",
    ) -> None:
        now = utc_now()
        async with session.begin():
            record = await session.scalar(
                select(AuthenticationSession)
                .where(AuthenticationSession.id == authentication_session_id)
                .with_for_update()
            )
            if record is None or record.user_id != actor_user_id:
                return
            if record.status in {"revoked", "compromised"}:
                return
            record.status = "revoked"
            record.revoked_at = now
            record.revocation_reason = reason
            record.revoked_by_user_id = actor_user_id
            await self._revoke_session_tokens(
                session, session_id=record.id, reason=reason, now=now
            )
            self.stage_security_event(
                session,
                event_type="session_revoked",
                success=True,
                user_id=record.user_id,
                authentication_session_id=record.id,
                occurred_at=now,
            )

    async def logout_all(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        reason: str = "user_logout_all",
    ) -> None:
        now = utc_now()
        async with session.begin():
            records = list(
                (
                    await session.scalars(
                        select(AuthenticationSession)
                        .where(
                            AuthenticationSession.user_id == user_id,
                            AuthenticationSession.status.in_(["active", "expired"]),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for record in records:
                record.status = "revoked"
                record.revoked_at = now
                record.revocation_reason = reason
                record.revoked_by_user_id = user_id
                await self._revoke_session_tokens(
                    session, session_id=record.id, reason=reason, now=now
                )
                self.stage_security_event(
                    session,
                    event_type="session_revoked",
                    success=True,
                    user_id=user_id,
                    authentication_session_id=record.id,
                    occurred_at=now,
                )

    @staticmethod
    async def revoke_user_sessions(
        session: AsyncSession,
        *,
        user_id: UUID,
        reason: str,
        now: datetime,
    ) -> None:
        records = list(
            (
                await session.scalars(
                    select(AuthenticationSession)
                    .where(
                        AuthenticationSession.user_id == user_id,
                        AuthenticationSession.status == "active",
                    )
                    .with_for_update()
                )
            ).all()
        )
        for record in records:
            record.status = "revoked"
            record.revoked_at = now
            record.revocation_reason = reason
            await AuthenticationService._revoke_session_tokens(
                session, session_id=record.id, reason=reason, now=now
            )

    @staticmethod
    async def _revoke_session_tokens(
        session: AsyncSession,
        *,
        session_id: UUID,
        reason: str,
        now: datetime,
    ) -> None:
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.session_id == session_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revocation_reason=reason)
        )

    async def _validate_session_records(
        self,
        session: AsyncSession,
        *,
        authentication_session: AuthenticationSession,
        now: datetime,
        lock: bool,
    ) -> tuple[User, UserCredential]:
        if (
            authentication_session.status != "active"
            or authentication_session.absolute_expires_at <= now
            or (
                authentication_session.idle_expires_at is not None
                and authentication_session.idle_expires_at <= now
            )
        ):
            raise SessionInvalidError("Session is invalid.")
        user_statement = select(User).where(User.id == authentication_session.user_id)
        credential_statement = select(UserCredential).where(
            UserCredential.user_id == authentication_session.user_id
        )
        if lock:
            user_statement = user_statement.with_for_update()
            credential_statement = credential_statement.with_for_update()
        user = await session.scalar(user_statement)
        credential = await session.scalar(credential_statement)
        if (
            user is None
            or credential is None
            or user.status != "active"
            or user.archived_at is not None
            or authentication_session.credential_version
            != credential.credential_version
            or authentication_session.authorization_version
            != user.authorization_version
        ):
            raise SessionInvalidError("Session is invalid.")
        return user, credential


class RecoveryService:
    def __init__(
        self,
        password_service: PasswordService,
        token_service: SecurityTokenService,
        configuration: Settings = settings,
    ) -> None:
        self.password_service = password_service
        self.token_service = token_service
        self.configuration = configuration

    async def request_password_reset(
        self,
        session: AsyncSession,
        *,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenDelivery:
        normalized_email = normalize_email(email)
        now = utc_now()
        plaintext_token: str | None = None
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.normalized_email == normalized_email)
            )
            if (
                user is not None
                and user.status == "active"
                and user.archived_at is None
            ):
                await session.execute(
                    update(PasswordResetToken)
                    .where(
                        PasswordResetToken.user_id == user.id,
                        PasswordResetToken.consumed_at.is_(None),
                        PasswordResetToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                plaintext_token = self.token_service.generate_token()
                session.add(
                    PasswordResetToken(
                        user_id=user.id,
                        token_hash=self.token_service.hash_token(plaintext_token),
                        issued_at=now,
                        expires_at=now
                        + timedelta(
                            seconds=self.configuration.password_reset_lifetime_seconds
                        ),
                        request_ip_address=ip_address,
                        request_user_agent=user_agent,
                    )
                )
            AuthenticationService.stage_security_event(
                session,
                event_type="password_reset_requested",
                success=True,
                user_id=user.id if user is not None else None,
                normalized_email=normalized_email,
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=now,
            )
        return TokenDelivery(plaintext_token)

    async def confirm_password_reset(
        self,
        session: AsyncSession,
        *,
        plaintext_token: str,
        new_password: str,
    ) -> None:
        encoded_hash = self.password_service.hash_password(new_password)
        token_hash = self.token_service.hash_token(plaintext_token)
        now = utc_now()
        async with session.begin():
            reset_token = await session.scalar(
                select(PasswordResetToken)
                .where(PasswordResetToken.token_hash == token_hash)
                .with_for_update()
            )
            if (
                reset_token is None
                or reset_token.expires_at <= now
                or reset_token.consumed_at is not None
                or reset_token.revoked_at is not None
            ):
                raise InvalidTokenError("Password reset token is invalid.")
            credential = await session.scalar(
                select(UserCredential)
                .where(UserCredential.user_id == reset_token.user_id)
                .with_for_update()
            )
            if credential is None:
                raise InvalidTokenError("Password reset token is invalid.")
            CredentialService(self.password_service)._apply_password_hash(
                credential, encoded_hash, now
            )
            reset_token.consumed_at = now
            await session.execute(
                update(PasswordResetToken)
                .where(
                    PasswordResetToken.user_id == reset_token.user_id,
                    PasswordResetToken.id != reset_token.id,
                    PasswordResetToken.consumed_at.is_(None),
                    PasswordResetToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            await AuthenticationService.revoke_user_sessions(
                session,
                user_id=reset_token.user_id,
                reason="password_reset",
                now=now,
            )
            AuthenticationService.stage_security_event(
                session,
                event_type="password_reset_completed",
                success=True,
                user_id=reset_token.user_id,
                occurred_at=now,
            )

    async def request_email_verification(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
    ) -> TokenDelivery:
        now = utc_now()
        async with session.begin():
            user = await session.scalar(
                select(User).where(User.id == user_id).with_for_update()
            )
            if user is None or user.status != "active" or user.archived_at is not None:
                raise InvalidTokenError("Email verification request is invalid.")
            await session.execute(
                update(EmailVerificationToken)
                .where(
                    EmailVerificationToken.user_id == user.id,
                    EmailVerificationToken.consumed_at.is_(None),
                    EmailVerificationToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            plaintext_token = self.token_service.generate_token()
            session.add(
                EmailVerificationToken(
                    user_id=user.id,
                    normalized_email=user.normalized_email,
                    token_hash=self.token_service.hash_token(plaintext_token),
                    issued_at=now,
                    expires_at=now
                    + timedelta(
                        seconds=self.configuration.email_verification_lifetime_seconds
                    ),
                )
            )
            AuthenticationService.stage_security_event(
                session,
                event_type="email_verification_requested",
                success=True,
                user_id=user.id,
                normalized_email=user.normalized_email,
                occurred_at=now,
            )
        return TokenDelivery(plaintext_token)

    async def confirm_email_verification(
        self,
        session: AsyncSession,
        *,
        plaintext_token: str,
    ) -> None:
        token_hash = self.token_service.hash_token(plaintext_token)
        now = utc_now()
        async with session.begin():
            verification_token = await session.scalar(
                select(EmailVerificationToken)
                .where(EmailVerificationToken.token_hash == token_hash)
                .with_for_update()
            )
            if (
                verification_token is None
                or verification_token.expires_at <= now
                or verification_token.consumed_at is not None
                or verification_token.revoked_at is not None
            ):
                raise InvalidTokenError("Email verification token is invalid.")
            user = await session.scalar(
                select(User)
                .where(User.id == verification_token.user_id)
                .with_for_update()
            )
            if (
                user is None
                or user.normalized_email != verification_token.normalized_email
                or user.status != "active"
                or user.archived_at is not None
            ):
                raise InvalidTokenError("Email verification token is invalid.")
            verification_token.consumed_at = now
            user.email_verified_at = now
            AuthenticationService.stage_security_event(
                session,
                event_type="email_verified",
                success=True,
                user_id=user.id,
                normalized_email=user.normalized_email,
                occurred_at=now,
            )


password_service = PasswordService()
security_token_service = SecurityTokenService()
access_token_service = AccessTokenService()
credential_service = CredentialService(password_service)
authentication_service = AuthenticationService(
    password_service,
    security_token_service,
    access_token_service,
)
recovery_service = RecoveryService(password_service, security_token_service)
