from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Asset(Base):
    __tablename__ = "operational_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_assets_branch",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "asset_class IN ('customer_equipment','vehicle','tool','equipment','other_supported_asset')",
            name="ck_assets_class",
        ),
        CheckConstraint(
            "lifecycle IN ('active','inactive','retired','replaced','disposed')",
            name="ck_assets_lifecycle",
        ),
        CheckConstraint("version >= 1", name="ck_assets_version"),
        UniqueConstraint("company_id", "asset_number", name="uq_assets_company_number"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_assets_command"),
        UniqueConstraint("company_id", "id", name="uq_assets_company_id"),
        Index(
            "ix_assets_search", "company_id", "branch_id", "asset_class", "lifecycle"
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_number: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    predecessor_asset_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("operational_assets.id", ondelete="RESTRICT")
    )
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    identity_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AssetEvidence(Base):
    __tablename__ = "operational_asset_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_evidence_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "evidence_type IN ('manufacturer','model','serial_reference','vin','license_plate','provider_identity','powertrain','odometer','condition','installation','removal','replacement','job_service','warranty','inspection','maintenance','readiness','document','custody')",
            name="ck_asset_evidence_type",
        ),
        CheckConstraint(
            "state IN ('recorded','verified','unverified','eligible','not_eligible','expired','conflicting_evidence','insufficient_evidence','scheduled','due','completed','canceled','deferred','pass','attention_required','fail','not_applicable','unable_to_verify')",
            name="ck_asset_evidence_state",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_evidence_command"
        ),
        UniqueConstraint(
            "company_id", "asset_id", "evidence_digest", name="uq_asset_evidence_digest"
        ),
        Index("ix_asset_evidence_history", "company_id", "asset_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_reference: Mapped[str | None] = mapped_column(String(240))
    protected_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AssetRelationship(Base):
    __tablename__ = "operational_asset_relationships"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_relationship_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "relationship_type IN ('customer','service_location','job','employee_custody','vehicle_custody','branch_custody','inventory_location','dispatch_context')",
            name="ck_asset_relationship_type",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from",
            name="ck_asset_relationship_period",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_relationship_command"
        ),
        Index(
            "ix_asset_relationship_active",
            "company_id",
            "asset_id",
            "relationship_type",
            "valid_to",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    related_entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AssetLifecycleEvidence(Base):
    __tablename__ = "operational_asset_lifecycle_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_lifecycle_asset",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_lifecycle_command"
        ),
        Index("ix_asset_lifecycle_history", "company_id", "asset_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    prior_state: Mapped[str] = mapped_column(String(20), nullable=False)
    resulting_state: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AssetActionEvidence(Base):
    """Immutable typed operational evidence used by ASSET.002–ASSET.009."""

    __tablename__ = "operational_asset_action_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "asset_id"],
            ["operational_assets.company_id", "operational_assets.id"],
            name="fk_asset_action_asset",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action_type IN ('equipment_install','equipment_remove','equipment_replace','warranty_evidence','warranty_review','service_link','vehicle_assignment','inspection','maintenance','out_of_service','custody_transfer','custody_return','document_binding')",
            name="ck_asset_action_type",
        ),
        CheckConstraint("asset_version >= 1", name="ck_asset_action_version"),
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_asset_action_command"
        ),
        UniqueConstraint(
            "company_id", "asset_id", "evidence_digest", name="uq_asset_action_digest"
        ),
        Index("ix_asset_action_history", "company_id", "asset_id", "occurred_at", "id"),
        Index(
            "ix_asset_action_queue",
            "company_id",
            "branch_id",
            "action_type",
            "occurred_at",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    related_entity_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    asset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
