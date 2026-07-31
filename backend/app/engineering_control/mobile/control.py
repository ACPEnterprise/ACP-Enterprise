from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringWorkstreamControl(Base):
    __tablename__ = "engineering_workstream_controls"
    __table_args__ = (
        ForeignKeyConstraint(
            ["actor_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_workstream_controls_actor_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "desired_state IN ('active','paused','cancelled')",
            name="ck_workstream_controls_desired_state",
        ),
        CheckConstraint("version >= 1", name="ck_workstream_controls_version"),
        UniqueConstraint(
            "company_id", "command_id", name="uq_workstream_controls_command"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "companies.id", name="fk_workstream_controls_company", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "engineering_commands.id",
            name="fk_workstream_controls_command",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    desired_state: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(240))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class WorkstreamControlRepository:
    @staticmethod
    async def get(
        session: AsyncSession, *, company_id: UUID, command_id: UUID
    ) -> EngineeringWorkstreamControl | None:
        return await session.scalar(
            select(EngineeringWorkstreamControl).where(
                EngineeringWorkstreamControl.company_id == company_id,
                EngineeringWorkstreamControl.command_id == command_id,
            )
        )

    @classmethod
    async def set_state(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        actor_user_id: UUID,
        desired_state: str,
        reason: str | None,
        occurred_at: datetime,
    ) -> EngineeringWorkstreamControl:
        record = await session.scalar(
            select(EngineeringWorkstreamControl)
            .where(
                EngineeringWorkstreamControl.company_id == company_id,
                EngineeringWorkstreamControl.command_id == command_id,
            )
            .with_for_update()
        )
        if record is None:
            record = EngineeringWorkstreamControl(
                company_id=company_id,
                command_id=command_id,
                actor_user_id=actor_user_id,
                desired_state=desired_state,
                reason=reason,
                created_at=occurred_at,
                updated_at=occurred_at,
            )
            session.add(record)
        else:
            record.desired_state = desired_state
            record.actor_user_id = actor_user_id
            record.reason = reason
            record.version += 1
            record.updated_at = occurred_at
        await session.flush()
        return record
