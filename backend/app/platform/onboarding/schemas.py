from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class OnboardingInitiateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_key: str = Field(min_length=1, max_length=128)
    branch_id: UUID
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    employee_type: str = Field(pattern="^(employee|contractor|vendor)$")
    employee_number_prefix: str = Field(min_length=1, max_length=20)
    employee_number_width: int = Field(ge=1, le=20)
    role_ids: tuple[UUID, ...] = ()
    additional_permission_ids: tuple[UUID, ...] = ()
    login_email: SecretStr | None = None
    existing_user_id: UUID | None = None

    @model_validator(mode="after")
    def one_login_source(self) -> "OnboardingInitiateRequest":
        if (self.login_email is None) == (self.existing_user_id is None):
            raise ValueError("exactly one login identity source is required")
        return self


class OnboardingActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=1024)
    password: str = Field(min_length=1, max_length=256)


class OnboardingView(BaseModel):
    id: UUID
    employee_id: UUID
    membership_id: UUID
    branch_id: UUID
    masked_login: str
    status: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OnboardingOwnerClaimView(BaseModel):
    """One-time non-Production handoff to an authorized onboarding owner."""

    activation_token: str = Field(min_length=20, max_length=1024)

    model_config = ConfigDict(extra="forbid")


class OnboardingDeliveryView(BaseModel):
    request_id: UUID
    invitation_id: UUID
    message_id: UUID | None
    invitation_status: str
    delivery_status: str
    template_version: str | None
    retry_count: int
    provider_reference_present: bool
    last_error_code: str | None
    created_at: datetime | None
    submitted_at: datetime | None
    delivered_at: datetime | None

    model_config = ConfigDict(extra="forbid")
