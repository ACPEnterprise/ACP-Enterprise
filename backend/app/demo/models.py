from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class DemoEnvironment(Base):
    """Stable per-representative identity whose disposable tenant can be replaced."""

    __tablename__ = "demo_environments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('provisioning','ready','resetting','disabled')",
            name="ck_demo_environment_status",
        ),
        UniqueConstraint("owner_user_id", name="uq_demo_environment_owner"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    owner_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    active_company_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT")
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="provisioning"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DemoScenario(Base):
    __tablename__ = "demo_scenarios"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_demo_scenario_company_code"),
        Index("ix_demo_scenario_company_position", "company_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    environment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("demo_environments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    guided_steps: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    condition: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    record_refs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class DemoFeedback(Base):
    __tablename__ = "demo_feedback"
    __table_args__ = (
        CheckConstraint(
            "category IN ('confusing','bug','missing_feature','customer_objection','sales_idea')",
            name="ck_demo_feedback_category",
        ),
        Index("ix_demo_feedback_company_created", "company_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    environment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("demo_environments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    page: Mapped[str] = mapped_column(String(240), nullable=False)
    scenario_code: Mapped[str | None] = mapped_column(String(80))
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    app_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
