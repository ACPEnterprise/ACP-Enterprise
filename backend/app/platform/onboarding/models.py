from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EmployeeNumberPolicy(Base):
    __tablename__ = "employee_number_policies"
    __table_args__ = (
        CheckConstraint("next_value >= 1", name="ck_employee_number_next_positive"),
        CheckConstraint("width BETWEEN 1 AND 20", name="ck_employee_number_width"),
        UniqueConstraint("company_id", name="uq_employee_number_policy_company"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class IdentityOnboardingRequest(Base):
    __tablename__ = "identity_onboarding_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','invited','activated','revoked')",
            name="ck_identity_onboarding_request_status",
        ),
        UniqueConstraint(
            "company_id", "request_key", name="uq_identity_onboarding_request_key"
        ),
        UniqueConstraint("employee_id", name="uq_identity_onboarding_employee"),
        ForeignKeyConstraint(
            ["company_id", "membership_id"],
            ["memberships.company_id", "memberships.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "branch_id"],
            ["branches.company_id", "branches.id"],
            name="fk_identity_onboarding_request_company_branch",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["company_id", "employee_id"],
            ["employees.company_id", "employees.id"],
            name="fk_identity_onboarding_request_company_employee",
            ondelete="RESTRICT",
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
    branch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    masked_login: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    initiated_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdentityOnboardingInvitation(Base):
    __tablename__ = "identity_onboarding_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','consumed','expired','revoked','superseded')",
            name="ck_identity_onboarding_invitation_status",
        ),
        UniqueConstraint("token_hash", name="uq_identity_onboarding_invitation_hash"),
        Index(
            "ix_identity_onboarding_invitation_request",
            "onboarding_request_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    onboarding_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_onboarding_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    issued_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_onboarding_invitations.id", ondelete="RESTRICT"),
    )
    safe_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class ProtectedInvitationDeliveryEnvelope(Base):
    __tablename__ = "protected_invitation_delivery_envelopes"
    __table_args__ = (
        UniqueConstraint(
            "invitation_id", name="uq_protected_invitation_envelope_invitation"
        ),
        CheckConstraint(
            "status IN ('pending','claimed','delivered','destroyed')",
            name="ck_protected_invitation_envelope_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    invitation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity_onboarding_invitations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    key_id: Mapped[str] = mapped_column(String(100), nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    destroyed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PreviewFixtureResource(Base):
    """Tenant-scoped ownership evidence for one sanctioned Preview fixture resource."""

    __tablename__ = "preview_fixture_resources"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "fixture_key",
            "resource_key",
            name="uq_preview_fixture_resource_key",
        ),
        UniqueConstraint(
            "company_id",
            "resource_type",
            "resource_id",
            name="uq_preview_fixture_resource_identity",
        ),
        CheckConstraint(
            "lifecycle IN ('active','released','audit_retained')",
            name="ck_preview_fixture_resource_lifecycle",
        ),
        CheckConstraint(
            "length(authority_digest) = 64",
            name="ck_preview_fixture_resource_authority_digest",
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
    fixture_key: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_key: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    authority_type: Mapped[str] = mapped_column(String(64), nullable=False)
    authority_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    authority_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    active_projection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
