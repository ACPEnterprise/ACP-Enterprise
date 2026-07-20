from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt

from app.core.config import Settings, settings
from app.platform.auth.errors import InvalidTokenError


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    credential_version: int
    authorization_version: int
    issued_at: datetime
    expires_at: datetime
    token_id: UUID


class AccessTokenService:
    required_claims = ["iss", "aud", "sub", "sid", "iat", "exp", "jti", "cv", "av"]

    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self._keys = configuration.access_token_keys
        self._active_kid = configuration.access_token_active_kid

    def issue(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        credential_version: int,
        authorization_version: int,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        issued_at = now or datetime.now(timezone.utc)
        expires_at = issued_at + timedelta(
            seconds=self.configuration.access_token_lifetime_seconds
        )
        claims: dict[str, Any] = {
            "iss": self.configuration.access_token_issuer,
            "aud": self.configuration.access_token_audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued_at,
            "exp": expires_at,
            "jti": str(uuid4()),
            "cv": credential_version,
            "av": authorization_version,
        }
        token = jwt.encode(
            claims,
            self._keys[self._active_kid],
            algorithm=self.configuration.access_token_algorithm,
            headers={"kid": self._active_kid},
        )
        return token, expires_at

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or kid not in self._keys:
                raise InvalidTokenError("Access token is invalid.")
            payload = jwt.decode(
                token,
                self._keys[kid],
                algorithms=[self.configuration.access_token_algorithm],
                audience=self.configuration.access_token_audience,
                issuer=self.configuration.access_token_issuer,
                options={"require": self.required_claims},
            )
            return AccessTokenClaims(
                user_id=UUID(payload["sub"]),
                session_id=UUID(payload["sid"]),
                credential_version=int(payload["cv"]),
                authorization_version=int(payload["av"]),
                issued_at=datetime.fromtimestamp(payload["iat"], timezone.utc),
                expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
                token_id=UUID(payload["jti"]),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
            raise InvalidTokenError("Access token is invalid.") from error
