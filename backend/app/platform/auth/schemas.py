from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.platform.auth.services import normalize_email


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictSchema):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    device_label: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return normalize_email(value)


class RefreshRequest(StrictSchema):
    refresh_token: str = Field(min_length=32, max_length=1024)


class PasswordResetRequest(StrictSchema):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return normalize_email(value)


class PasswordResetConfirmRequest(StrictSchema):
    token: str = Field(min_length=32, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class EmailVerificationConfirmRequest(StrictSchema):
    token: str = Field(min_length=32, max_length=1024)


class UserIdentityResponse(StrictSchema):
    id: UUID
    normalized_email: str
    first_name: str
    last_name: str
    display_name: str
    email_verified_at: datetime | None


class AuthenticationResponse(StrictSchema):
    token_type: str = "bearer"
    user: UserIdentityResponse
    session_id: UUID
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
    session_absolute_expires_at: datetime | None = None
    session_idle_expires_at: datetime | None = None


class GenericResponse(StrictSchema):
    message: str
    development_token: str | None = None


class SessionResponse(StrictSchema):
    user: UserIdentityResponse
    session_id: UUID
    status: str
    created_at: datetime
    last_seen_at: datetime
    absolute_expires_at: datetime
    idle_expires_at: datetime | None
    authentication_method: str
