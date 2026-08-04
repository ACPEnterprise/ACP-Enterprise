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

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class OptionCreate(PriceBookSchema):
    service_item_id: UUID
    label: str = Field(min_length=1, max_length=160)
    position: int = Field(ge=1)


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
