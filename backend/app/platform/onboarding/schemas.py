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
    create_employee: bool = False
    employee_type: str | None = Field(
        default=None, pattern="^(employee|contractor|vendor)$"
    )
    employee_number_prefix: str | None = Field(
        default=None, min_length=1, max_length=20
    )
    employee_number_width: int | None = Field(default=None, ge=1, le=20)
    role_ids: tuple[UUID, ...] = ()
    login_email: SecretStr | None = None
    existing_user_id: UUID | None = None

    @model_validator(mode="after")
    def one_login_source(self) -> "OnboardingInitiateRequest":
        if (self.login_email is None) == (self.existing_user_id is None):
            raise ValueError("exactly one login identity source is required")
        employee_fields = (
            self.employee_type,
            self.employee_number_prefix,
            self.employee_number_width,
        )
        if self.create_employee != all(value is not None for value in employee_fields):
            raise ValueError("employee fields are required only for Employee linkage")
        return self


class OnboardingActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=1024)
    password: str = Field(min_length=1, max_length=256)


class OnboardingView(BaseModel):
    id: UUID
    user_id: UUID
    employee_id: UUID | None
    membership_id: UUID
    branch_id: UUID
    masked_login: str
    status: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class OnboardingListView(OnboardingView):
    created_at: datetime


class OnboardingOption(BaseModel):
    id: UUID
    code: str
    name: str


class OnboardingOptionsView(BaseModel):
    branches: list[OnboardingOption]
    roles: list[OnboardingOption]
