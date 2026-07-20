from datetime import datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


PendingEmailChangeStatus = Literal[
    "pending", "confirmed", "revoked", "superseded", "expired"
]


class IdentityApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmailAvailabilityRequest(IdentityApiSchema):
    email: str = Field(
        min_length=3,
        max_length=320,
        description="Proposed login email address.",
        examples=["owner@example.com"],
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("email address is invalid")
        return normalized


class EmailAvailabilityResponse(IdentityApiSchema):
    available: bool = Field(description="Whether the email can currently be requested.")


class AdministrativeEmailChangeRequest(IdentityApiSchema):
    email: str = Field(
        min_length=3,
        max_length=320,
        description="New login email requiring verification.",
        examples=["new.owner@example.com"],
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return EmailAvailabilityRequest.validate_email(value)


class EmailChangeConfirmationRequest(IdentityApiSchema):
    token: str = Field(
        min_length=32,
        max_length=1024,
        description="One-time email-change verification token.",
        examples=["verification-token-delivered-out-of-band"],
    )


class PendingEmailChangeResponse(IdentityApiSchema):
    id: UUID = Field(description="Stable pending-change identifier.")
    proposed_email: str = Field(description="Normalized proposed login email.")
    status: PendingEmailChangeStatus
    created_at: datetime
    expires_at: datetime
    confirmed_at: datetime | None = None
    revoked_at: datetime | None = None
    superseded_at: datetime | None = None
    expired_at: datetime | None = None


class EmailChangeRequestResponse(IdentityApiSchema):
    change: PendingEmailChangeResponse
    created: bool = Field(description="Whether a new request was created.")
    development_token: str | None = Field(
        default=None,
        description=(
            "Development/test delivery token; always omitted in secure environments."
        ),
    )


class IdentityUserResponse(IdentityApiSchema):
    id: UUID
    normalized_email: str
    email_verified_at: datetime | None


class ForcedPasswordResetRequest(IdentityApiSchema):
    reason_code: Literal[
        "administrator_required",
        "security_incident",
        "credential_recovery",
        "policy_compliance",
    ] = Field(
        description="Controlled reason for requiring a password change.",
        examples=["administrator_required"],
    )


class ForcedPasswordResetResponse(IdentityApiSchema):
    required: bool
    changed: bool
    required_at: datetime | None
    reason_code: str | None
    cleared_at: datetime | None
    credential_version: int = Field(ge=1)


class IdentityStateResponse(IdentityApiSchema):
    user_id: UUID
    normalized_email: str
    email_verified_at: datetime | None
    pending_email_change: PendingEmailChangeResponse | None
    password_change_required: bool
    password_change_required_at: datetime | None
    password_change_required_reason_code: str | None
    password_change_required_cleared_at: datetime | None
    credential_version: int = Field(ge=1)
    authorization_version: int = Field(ge=1)


class IdentityMutationResponse(IdentityApiSchema):
    changed: bool
    message: str
