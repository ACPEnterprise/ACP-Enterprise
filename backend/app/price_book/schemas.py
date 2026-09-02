from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PriceBookSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CategoryCreate(PriceBookSchema):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: UUID | None = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class TaxClassificationCreate(PriceBookSchema):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    taxable: bool

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class ServiceItemCreate(PriceBookSchema):
    branch_id: UUID | None = None
    category_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    customer_description: str = Field(min_length=1, max_length=4000)
    internal_description: str | None = Field(default=None, max_length=4000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class ComponentCreate(PriceBookSchema):
    component_type: str = Field(pattern=r"^(labor|material)$")
    code: str | None = Field(default=None, max_length=100)
    label: str = Field(min_length=1, max_length=240)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class PriceVersionCreate(PriceBookSchema):
    branch_id: UUID | None = None
    tax_classification_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_price: Decimal = Field(ge=0)
    effective_at: datetime
    expires_at: datetime | None = None
    components: tuple[ComponentCreate, ...] = ()


class ActivationRequest(PriceBookSchema):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class LifecycleRequest(PriceBookSchema):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class PriceVersionUpdate(PriceBookSchema):
    expected_version: int = Field(ge=1)
    tax_classification_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit_price: Decimal = Field(ge=0)
    effective_at: datetime
    expires_at: datetime | None = None
    components: tuple[ComponentCreate, ...] = ()


class SnapshotRequest(PriceBookSchema):
    branch_id: UUID
    quantity: Decimal = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_at: datetime
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")
    option_group_id: UUID | None = None
    option_id: UUID | None = None
    historical: bool = False


class OptionGroupCreate(PriceBookSchema):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    minimum_selections: int = Field(default=0, ge=0)
    maximum_selections: int = Field(default=1, ge=1)

    @field_validator("maximum_selections")
    @classmethod
    def validate_bounds(cls, value: int, info) -> int:
        minimum = info.data.get("minimum_selections", 0)
        if value < minimum:
            raise ValueError("Maximum selections must be at least minimum selections.")
        return value

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class OptionCreate(PriceBookSchema):
    service_item_id: UUID
    label: str = Field(min_length=1, max_length=160)
    position: int = Field(ge=1)


class ReviewBatchCreate(PriceBookSchema):
    configuration_version: str = Field(min_length=1, max_length=120)
    review_type: str = Field(
        pattern=r"^(commercial_content|candidate_prices|tax_classification|membership|source_conflict)$"
    )
    selector: dict[str, object]
    service_codes: tuple[str, ...] = Field(min_length=1, max_length=500)
    exclusions: tuple[str, ...] = Field(default=(), max_length=500)
    candidate_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9._:-]{8,128}$")


class ReviewBatchDecision(PriceBookSchema):
    expected_version: int = Field(ge=1)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: str = Field(pattern=r"^(approved|returned|excluded)$")
    reason: str = Field(min_length=1, max_length=500)


class ReviewBatchItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    configuration_version: str
    review_type: str
    selector: dict[str, object]
    service_codes: list[str]
    exclusions: list[str]
    candidate_set_digest: str
    status: str
    decision_reason: str | None
    idempotency_key: str
    version: int
    created_by_user_id: UUID
    decided_by_user_id: UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdjustmentProposalCreate(PriceBookSchema):
    source_price_book_version: str = Field(min_length=1, max_length=120)
    recommendation_identity: str = Field(min_length=1, max_length=160)
    economics_evidence_version: str | None = Field(default=None, max_length=160)
    model_version: str | None = Field(default=None, max_length=160)
    affected_service_codes: tuple[str, ...] = Field(min_length=1, max_length=500)
    owner_exclusions: tuple[str, ...] = Field(default=(), max_length=500)
    transformation_kind: str = Field(
        pattern=r"^(percentage|fixed_amount|markup_policy)$"
    )
    transformation: dict[str, object]
    impacts: tuple[dict[str, object], ...] = Field(min_length=1, max_length=500)
    limitations: tuple[str, ...] = Field(default=(), max_length=100)
    effective_at: datetime
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AdjustmentProposalDecision(PriceBookSchema):
    expected_version: int = Field(ge=1)
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: str = Field(pattern=r"^(approved|returned|rejected)$")
    reason: str = Field(min_length=1, max_length=500)


class AdjustmentProposalItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    source_price_book_version: str
    recommendation_identity: str
    economics_evidence_version: str | None
    model_version: str | None
    affected_service_codes: list[str]
    owner_exclusions: list[str]
    transformation_kind: str
    transformation: dict[str, object]
    impacts: list[dict[str, object]]
    limitations: list[str]
    effective_at: datetime
    proposal_digest: str
    status: str
    version: int
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CategoryItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    parent_id: UUID | None
    code: str
    name: str
    description: str | None
    status: str
    version: int


class TaxClassificationItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    code: str
    name: str
    taxable: bool
    status: str
    version: int


class ServiceItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    category_id: UUID
    code: str
    name: str
    customer_description: str
    status: str
    current_version_id: UUID | None
    version: int


class ComponentItem(PriceBookSchema):
    id: UUID
    component_type: str
    code: str | None
    label: str
    quantity: Decimal
    position: int


class PriceVersionItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    service_item_id: UUID
    branch_id: UUID | None
    tax_classification_id: UUID
    revision: int
    currency: str
    unit_price: Decimal
    effective_at: datetime
    expires_at: datetime | None
    status: str
    rounding_mode: str
    version: int
    components: tuple[ComponentItem, ...] = ()


class SnapshotItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    branch_id: UUID
    service_item_id: UUID
    price_version_id: UUID
    quantity: Decimal
    unit_price: Decimal
    extended_amount: Decimal
    currency: str
    effective_at: datetime
    snapshot_data: dict[str, object]
    digest: str
    idempotency_key: str
    created_at: datetime


class AuditItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    actor_user_id: UUID
    prior_state: dict[str, object] | None
    new_state: dict[str, object]
    reason: str
    version: int
    occurred_at: datetime


class OptionGroupItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    code: str
    name: str
    status: str
    minimum_selections: int
    maximum_selections: int


class OptionItem(PriceBookSchema):
    id: UUID
    company_id: UUID
    option_group_id: UUID
    service_item_id: UUID
    label: str
    position: int


class CatalogPage(PriceBookSchema):
    categories: tuple[CategoryItem, ...]
    tax_classifications: tuple[TaxClassificationItem, ...]
    service_items: tuple[ServiceItem, ...]
    versions: tuple[PriceVersionItem, ...]
    option_groups: tuple[OptionGroupItem, ...]
    options: tuple[OptionItem, ...]
