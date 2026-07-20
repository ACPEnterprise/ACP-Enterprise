from collections.abc import Mapping
import os
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class BootstrapConfiguration(BaseModel):
    """Validated inputs loaded only by the explicit bootstrap command."""

    company_name: str = Field(min_length=1, max_length=200)
    company_code: str = Field(min_length=1, max_length=50)
    company_timezone: str = Field(min_length=1, max_length=100)
    branch_name: str = Field(min_length=1, max_length=200)
    branch_code: str = Field(min_length=1, max_length=50)
    administrator_email: str = Field(min_length=3, max_length=320)
    administrator_first_name: str = Field(min_length=1, max_length=100)
    administrator_last_name: str = Field(min_length=1, max_length=100)
    administrator_display_name: str | None = Field(default=None, max_length=200)
    administrator_password: SecretStr

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "company_name",
        "company_timezone",
        "branch_name",
        "administrator_first_name",
        "administrator_last_name",
    )
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("company_code", "branch_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized

    @field_validator("administrator_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("administrator email is invalid")
        return normalized

    @field_validator("administrator_display_name")
    @classmethod
    def strip_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("display name must not be blank")
        return normalized

    @model_validator(mode="after")
    def populate_display_name(self) -> "BootstrapConfiguration":
        if self.administrator_display_name is None:
            self.administrator_display_name = (
                f"{self.administrator_first_name} {self.administrator_last_name}"
            )
        return self


BOOTSTRAP_ENVIRONMENT_FIELDS = {
    f"BOOTSTRAP_{field_name.upper()}": field_name
    for field_name in BootstrapConfiguration.model_fields
}


def load_bootstrap_configuration(
    environment: Mapping[str, str] | None = None,
) -> BootstrapConfiguration:
    source = os.environ if environment is None else environment
    values = {
        field_name: source[environment_name]
        for environment_name, field_name in BOOTSTRAP_ENVIRONMENT_FIELDS.items()
        if environment_name in source
    }
    return BootstrapConfiguration.model_validate(values)
