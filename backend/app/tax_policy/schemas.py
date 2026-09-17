from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyTaxPolicySchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CompanyTaxPolicyCreate(CompanyTaxPolicySchema):
    policy_identity: str = Field(min_length=1, max_length=100)
    effective_at: datetime
    customer_service_treatment: str = Field(
        pattern=r"^(NOT_TAXED|TAXED|REVIEW_REQUIRED)$"
    )
    customer_material_treatment: str = Field(
        pattern=r"^(NOT_TAXED|TAXED|REVIEW_REQUIRED)$"
    )
    purchase_material_tax_handling: str = Field(
        pattern=r"^(PAID_AT_PURCHASE|EXEMPT|REVIEW_REQUIRED)$"
    )
    authority_source: str = Field(min_length=1, max_length=80)
    authority_notes: str | None = Field(default=None, max_length=4000)
    authorized_exceptions: list[dict[str, object]] = Field(default_factory=list)


class CompanyTaxPolicyUpdate(CompanyTaxPolicyCreate):
    expected_version: int = Field(ge=1)


class CompanyTaxPolicyCertify(CompanyTaxPolicySchema):
    expected_version: int = Field(ge=1)
    certification_reason: str = Field(min_length=1, max_length=500)


class CompanyTaxPolicyItem(CompanyTaxPolicySchema):
    id: UUID
    company_id: UUID
    policy_identity: str
    version: int
    status: str
    effective_at: datetime
    expires_at: datetime | None
    customer_service_treatment: str
    customer_material_treatment: str
    purchase_material_tax_handling: str
    authority_source: str
    authority_notes: str | None
    authorized_exceptions: list[dict[str, object]]
    supersedes_policy_id: UUID | None
    certified_by_user_id: UUID | None
    certified_at: datetime | None
    created_at: datetime


class CompanyTaxPolicyPage(CompanyTaxPolicySchema):
    current: CompanyTaxPolicyItem | None
    history: list[CompanyTaxPolicyItem]
