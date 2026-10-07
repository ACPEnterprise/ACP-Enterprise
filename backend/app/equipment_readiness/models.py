from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EquipmentCatalogItem(Base):
    __tablename__ = "equipment_readiness_catalog_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"], ["branches.company_id", "branches.id"],
            name="fk_equipment_catalog_branch", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "item_kind IN ('controlled_asset','equipment_set','non_serialized_item')",
            name="ck_equipment_catalog_kind",
        ),
        CheckConstraint("status IN ('active','inactive')", name="ck_equipment_catalog_status"),
        UniqueConstraint("company_id", "code", name="uq_equipment_catalog_company_code"),
        UniqueConstraint("company_id", "id", name="uq_equipment_catalog_company_id"),
        UniqueConstraint("company_id", "branch_id", "id", name="uq_equipment_catalog_scope_id"),
        Index("ix_equipment_catalog_scope", "company_id", "branch_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    capability_code: Mapped[str] = mapped_column(String(100), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    serialization_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EquipmentSetComponent(Base):
    __tablename__ = "equipment_readiness_set_components"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "catalog_item_id"],
            ["equipment_readiness_catalog_items.company_id", "equipment_readiness_catalog_items.id"],
            name="fk_equipment_component_catalog", ondelete="RESTRICT",
        ),
        CheckConstraint("required_quantity > 0", name="ck_equipment_component_quantity"),
        UniqueConstraint("company_id", "catalog_item_id", "component_code", name="uq_equipment_component_code"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    catalog_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    component_code: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    required_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EquipmentPlacement(Base):
    """Current projection; immutable custody events retain every transition."""
    __tablename__ = "equipment_readiness_placements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id", "catalog_item_id"],
            ["equipment_readiness_catalog_items.company_id", "equipment_readiness_catalog_items.branch_id", "equipment_readiness_catalog_items.id"],
            name="fk_equipment_placement_catalog", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "current_custodian_employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_equipment_placement_custodian", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "asset_id"], ["operational_assets.company_id", "operational_assets.id"],
            name="fk_equipment_placement_asset", ondelete="RESTRICT",
        ),
        CheckConstraint("home_kind IN ('vehicle','shop','warehouse','repair_vendor','other')", name="ck_equipment_home_kind"),
        CheckConstraint("current_location_kind IN ('vehicle','employee','shop','warehouse','repair_vendor','other','unknown')", name="ck_equipment_location_kind"),
        CheckConstraint("readiness_state IN ('ready','unknown','incomplete','out_of_service','missing')", name="ck_equipment_placement_readiness"),
        CheckConstraint("version >= 1", name="ck_equipment_placement_version"),
        UniqueConstraint("company_id", "catalog_item_id", "asset_id", name="uq_equipment_placement_identity"),
        UniqueConstraint("company_id", "id", name="uq_equipment_placement_company_id"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_placement_idempotency"),
        Index("ix_equipment_placement_custodian", "company_id", "current_custodian_employee_id", "readiness_state"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    catalog_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    home_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    home_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    current_location_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    current_location_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    current_custodian_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    custody_effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    readiness_state: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")
    service_state: Mapped[str] = mapped_column(String(40), nullable=False, default="available")
    missing_components: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EquipmentCustodyEvent(Base):
    __tablename__ = "equipment_readiness_custody_events"
    __table_args__ = (
        ForeignKeyConstraint(["company_id", "placement_id"], ["equipment_readiness_placements.company_id", "equipment_readiness_placements.id"], name="fk_equipment_custody_placement", ondelete="RESTRICT"),
        CheckConstraint("event_type IN ('assigned','transferred','received','returned','repair','broken','lost','confirmation','correction')", name="ck_equipment_custody_event_type"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_custody_idempotency"),
        Index("ix_equipment_custody_history", "company_id", "placement_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    placement_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    from_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    to_employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    from_location_kind: Mapped[str | None] = mapped_column(String(24))
    to_location_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    to_location_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    source_state: Mapped[str] = mapped_column(String(24), nullable=False)
    resulting_state: Mapped[str] = mapped_column(String(24), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EquipmentDailyConfirmation(Base):
    __tablename__ = "equipment_readiness_daily_confirmations"
    __table_args__ = (
        CheckConstraint("state IN ('present_ready','transferred','left_at_shop','in_repair','missing_or_unknown','incomplete_set','broken_or_out_of_service','other')", name="ck_equipment_confirmation_state"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_equipment_confirmation_idempotency"),
        Index("ix_equipment_confirmation_day", "company_id", "employee_id", "work_date", "catalog_item_id"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    catalog_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("equipment_readiness_catalog_items.id", ondelete="RESTRICT"), nullable=False)
    placement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("equipment_readiness_placements.id", ondelete="RESTRICT"))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(36), nullable=False)
    missing_components: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    note: Mapped[str | None] = mapped_column(String(500))
    supersedes_confirmation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("equipment_readiness_daily_confirmations.id", ondelete="RESTRICT"))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)


class ServiceEquipmentRequirement(Base):
    __tablename__ = "service_equipment_requirements"
    __table_args__ = (
        CheckConstraint("source_type IN ('price_book_service','job','service_template')", name="ck_service_equipment_source_type"),
        CheckConstraint("status IN ('active','inactive')", name="ck_service_equipment_status"),
        UniqueConstraint("company_id", "source_type", "source_entity_id", "capability_code", name="uq_service_equipment_requirement"),
        Index("ix_service_equipment_source", "company_id", "source_type", "source_entity_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    capability_code: Mapped[str] = mapped_column(String(100), nullable=False)
    requirement_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EquipmentAttention(Base):
    __tablename__ = "equipment_readiness_attention"
    __table_args__ = (
        CheckConstraint("priority IN ('critical_before_job','needs_attention','information')", name="ck_equipment_attention_priority"),
        CheckConstraint("state IN ('open','resolved','superseded')", name="ck_equipment_attention_state"),
        UniqueConstraint("company_id", "identity_key", name="uq_equipment_attention_identity"),
        Index("ix_equipment_attention_queue", "company_id", "branch_id", "state", "priority"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    identity_key: Mapped[str] = mapped_column(String(200), nullable=False)
    attention_code: Mapped[str] = mapped_column(String(80), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    employee_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    catalog_item_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    placement_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    appointment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    responsibility_code: Mapped[str] = mapped_column(String(80), nullable=False, default="FIELD_OPERATIONS")
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    resolution_note: Mapped[str | None] = mapped_column(String(500))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
