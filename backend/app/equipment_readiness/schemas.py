from datetime import date, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CatalogCreate(Schema):
    branch_id: UUID
    code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=200)
    capability_code: str = Field(min_length=1, max_length=100)
    item_kind: str = Field(pattern=r"^(controlled_asset|equipment_set|non_serialized_item)$")
    serialization_required: bool = False
    provenance: dict[str, object] = Field(default_factory=dict)


class CatalogOut(Schema):
    id: UUID
    branch_id: UUID
    code: str
    display_name: str
    capability_code: str
    item_kind: str
    serialization_required: bool
    status: str
    provenance: dict[str, object]


class ComponentCreate(Schema):
    component_code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=160)
    required_quantity: int = Field(default=1, ge=1, le=100)


class ComponentOut(Schema):
    id: UUID
    catalog_item_id: UUID
    component_code: str
    display_name: str
    required_quantity: int


class PlacementCreate(Schema):
    branch_id: UUID
    catalog_item_id: UUID
    asset_id: UUID | None = None
    home_kind: str = Field(pattern=r"^(vehicle|shop|warehouse|repair_vendor|other)$")
    home_entity_id: UUID | None = None
    current_location_kind: str = Field(pattern=r"^(vehicle|employee|shop|warehouse|repair_vendor|other|unknown)$")
    current_location_entity_id: UUID | None = None
    current_custodian_employee_id: UUID | None = None
    effective_at: AwareDatetime
    idempotency_key: str = Field(min_length=8, max_length=160, pattern=r"^[A-Za-z0-9.:-]+$")


class PlacementOut(Schema):
    id: UUID
    branch_id: UUID
    catalog_item_id: UUID
    asset_id: UUID | None
    home_kind: str
    home_entity_id: UUID | None
    current_location_kind: str
    current_location_entity_id: UUID | None
    current_custodian_employee_id: UUID | None
    custody_effective_at: datetime
    last_confirmed_at: datetime | None
    readiness_state: str
    service_state: str
    missing_components: list[object]
    version: int


class ConfirmationItem(Schema):
    catalog_item_id: UUID
    placement_id: UUID | None = None
    state: str = Field(pattern=r"^(present_ready|transferred|left_at_shop|in_repair|missing_or_unknown|incomplete_set|broken_or_out_of_service|other)$")
    missing_components: list[str] = Field(default_factory=list, max_length=50)
    note: str | None = Field(default=None, max_length=500)
    receiving_employee_id: UUID | None = None
    receiving_location_kind: str | None = Field(default=None, pattern=r"^(vehicle|employee|shop|warehouse|repair_vendor|other|unknown)$")
    receiving_location_entity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_disposition(self):
        if self.state == "incomplete_set" and not self.missing_components:
            raise ValueError("Incomplete equipment sets require missing component evidence")
        if self.state == "transferred" and not (
            self.receiving_employee_id or self.receiving_location_entity_id
        ):
            raise ValueError("Transfers require a receiving Employee or governed location")
        return self


class DailyConfirmationRequest(Schema):
    employee_id: UUID
    work_date: date
    confirmed_at: AwareDatetime
    items: tuple[ConfirmationItem, ...] = Field(min_length=1, max_length=50)
    idempotency_key: str = Field(min_length=8, max_length=150, pattern=r"^[A-Za-z0-9.:-]+$")


class ConfirmationOut(Schema):
    id: UUID
    employee_id: UUID
    catalog_item_id: UUID
    placement_id: UUID | None
    work_date: date
    state: str
    missing_components: list[object]
    note: str | None
    confirmed_at: datetime
    evidence_digest: str


class PromptItem(Schema):
    catalog_item_id: UUID
    code: str
    display_name: str
    item_kind: str
    placement_id: UUID | None
    default_state: str
    readiness_state: str
    last_confirmed_at: datetime | None


class DailyPrompt(Schema):
    employee_id: UUID
    work_date: date
    required: bool
    reason: str
    already_confirmed: bool
    items: tuple[PromptItem, ...]


class EquipmentChecklistSetting(Schema):
    equipment_checklist_requirement: str = Field(
        pattern=r"^(not_required|required_at_clock_in)$"
    )


class EquipmentChecklistSettingOut(Schema):
    employee_id: UUID
    equipment_checklist_requirement: str


class CustodyTransferRequest(Schema):
    to_employee_id: UUID | None = None
    to_location_kind: str = Field(pattern=r"^(vehicle|employee|shop|warehouse|repair_vendor|other|unknown)$")
    to_location_entity_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=500)
    event_type: str = Field(pattern=r"^(transferred|received|returned|repair|broken|lost|correction)$")
    resulting_state: str = Field(pattern=r"^(ready|unknown|incomplete|out_of_service|missing)$")
    occurred_at: AwareDatetime
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=160)


class CustodyEventOut(Schema):
    id: UUID
    placement_id: UUID
    event_type: str
    from_employee_id: UUID | None
    to_employee_id: UUID | None
    to_location_kind: str
    to_location_entity_id: UUID | None
    reason: str
    source_state: str
    resulting_state: str
    occurred_at: datetime
    evidence_digest: str


class RequirementCreate(Schema):
    branch_id: UUID
    source_type: str = Field(pattern=r"^(price_book_service|job|service_template)$")
    source_entity_id: UUID
    capability_code: str = Field(min_length=1, max_length=100)
    requirement_reason: str = Field(min_length=1, max_length=500)
    provenance: dict[str, object] = Field(default_factory=dict)


class RequirementOut(Schema):
    id: UUID
    branch_id: UUID
    source_type: str
    source_entity_id: UUID
    capability_code: str
    requirement_reason: str
    status: str
    provenance: dict[str, object]


class ReadinessItem(Schema):
    employee_id: UUID
    employee_name: str
    branch_id: UUID
    state: str
    warning_codes: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    scheduling_eligible: bool | None = None


class JobFit(Schema):
    job_id: UUID
    employee_id: UUID
    state: str
    soft_warning: bool
    required_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    continuation_allowed: bool = True
    override_reason_required: bool = False


class AttentionOut(Schema):
    id: UUID
    branch_id: UUID
    attention_code: str
    priority: str
    state: str
    employee_id: UUID | None
    catalog_item_id: UUID | None
    job_id: UUID | None
    appointment_id: UUID | None
    title: str
    explanation: str
    responsibility_code: str
    first_observed_at: datetime
    last_observed_at: datetime
    evidence_digest: str


class ResolveAttentionRequest(Schema):
    resolution_note: str = Field(min_length=1, max_length=500)
    expected_version: int = Field(ge=1)


class RefreshUpcomingRequest(Schema):
    branch_id: UUID
    as_of: AwareDatetime
    horizon_hours: int = Field(default=24, ge=1, le=168)


class IntelligenceEvidence(Schema):
    authority: str = "EQUIPMENT_READINESS"
    mutation_authority: str = "NONE"
    as_of: datetime
    attention_count: int
    impacted_job_count: int
    readiness_counts: dict[str, int]
    limitations: tuple[str, ...]
