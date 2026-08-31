from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engineering_control.workstream_runtime import EngineeringWorkstreamEvent
from app.platform.permissions.authorization import AuthorizationContext


class EngineeringMissionNotification(Base):
    __tablename__ = "engineering_mission_notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "event_id", "command_id"],
            [
                "engineering_workstream_events.company_id",
                "engineering_workstream_events.id",
                "engineering_workstream_events.command_id",
            ],
            name="fk_mission_notifications_event_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["acknowledged_by_user_id", "company_id"],
            ["memberships.user_id", "memberships.company_id"],
            name="fk_mission_notifications_ack_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('waiting_for_owner','completed','failed','recovering',"
            "'heartbeat_expired','worker_disconnected','deployment_completed',"
            "'deployment_failed','manual_recovery')",
            name="ck_mission_notification_kind",
        ),
        CheckConstraint(
            "severity IN ('information','warning','critical')",
            name="ck_mission_notification_severity",
        ),
        CheckConstraint(
            "status IN ('unread','read','acknowledged','archived')",
            name="ck_mission_notification_status",
        ),
        CheckConstraint("version >= 1", name="ck_mission_notification_version"),
        UniqueConstraint(
            "company_id", "event_id", name="uq_mission_notification_event"
        ),
        Index(
            "ix_mission_notification_company_status",
            "company_id",
            "status",
            "created_at",
            "id",
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
    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unread")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


def notification_kind(event: EngineeringWorkstreamEvent) -> str | None:
    if event.runtime_state == "waiting_for_owner":
        return "waiting_for_owner"
    if event.runtime_state == "recovering" and event.reason_code in {
        "reconciliation_required",
        "ambiguous_interrupted_execution",
    }:
        return "manual_recovery"
    return None


def notification_severity(kind: str) -> str:
    if kind in {"waiting_for_owner", "manual_recovery"}:
        return "warning"
    return "information"


class MissionNotificationService:
    async def list(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        page: int,
        page_size: int,
        now: datetime | None = None,
    ) -> tuple[tuple[EngineeringMissionNotification, ...], int]:
        observed_at = now or datetime.now(timezone.utc)
        async with db.begin():
            await self._materialize(db, company_id=context.company.id)
            await self._escalate(db, company_id=context.company.id, now=observed_at)
            rows = tuple(
                (
                    await db.scalars(
                        select(EngineeringMissionNotification)
                        .where(
                            EngineeringMissionNotification.company_id
                            == context.company.id
                        )
                        .order_by(
                            EngineeringMissionNotification.status.desc(),
                            EngineeringMissionNotification.created_at.desc(),
                            EngineeringMissionNotification.id,
                        )
                        .offset((page - 1) * page_size)
                        .limit(page_size)
                    )
                ).all()
            )
            from sqlalchemy import func

            total = int(
                await db.scalar(
                    select(func.count(EngineeringMissionNotification.id)).where(
                        EngineeringMissionNotification.company_id == context.company.id
                    )
                )
                or 0
            )
        return rows, total

    async def acknowledge(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        notification_id: UUID,
        expected_version: int,
        now: datetime | None = None,
    ) -> EngineeringMissionNotification:
        acknowledged_at = now or datetime.now(timezone.utc)
        async with db.begin():
            record = await db.scalar(
                select(EngineeringMissionNotification)
                .where(
                    EngineeringMissionNotification.company_id == context.company.id,
                    EngineeringMissionNotification.id == notification_id,
                )
                .with_for_update()
            )
            if record is None:
                raise LookupError("Mission Control notification was not found.")
            if record.status == "acknowledged":
                return record
            if record.version != expected_version:
                raise ValueError("Mission Control notification version is stale.")
            record.status = "acknowledged"
            record.acknowledged_at = acknowledged_at
            record.acknowledged_by_user_id = context.user.id
            record.version += 1
            await db.flush()
        return record

    async def transition(
        self,
        db: AsyncSession,
        *,
        context: AuthorizationContext,
        notification_id: UUID,
        expected_version: int,
        action: str,
        now: datetime | None = None,
    ) -> EngineeringMissionNotification:
        if action not in {"read", "archive"}:
            raise ValueError("Unsupported notification action.")
        changed_at = now or datetime.now(timezone.utc)
        async with db.begin():
            record = await db.scalar(
                select(EngineeringMissionNotification)
                .where(
                    EngineeringMissionNotification.company_id == context.company.id,
                    EngineeringMissionNotification.id == notification_id,
                )
                .with_for_update()
            )
            if record is None:
                raise LookupError("Mission Control notification was not found.")
            target = "read" if action == "read" else "archived"
            if record.status == target or (
                action == "read" and record.status != "unread"
            ):
                return record
            if record.version != expected_version:
                raise ValueError("Mission Control notification version is stale.")
            record.status = target
            if action == "read":
                record.read_at = changed_at
            else:
                record.archived_at = changed_at
                record.read_at = record.read_at or changed_at
            record.version += 1
            await db.flush()
        return record

    async def _materialize(self, db: AsyncSession, *, company_id: UUID) -> None:
        existing = select(EngineeringMissionNotification.event_id).where(
            EngineeringMissionNotification.company_id == company_id
        )
        events = tuple(
            (
                await db.scalars(
                    select(EngineeringWorkstreamEvent).where(
                        EngineeringWorkstreamEvent.company_id == company_id,
                        EngineeringWorkstreamEvent.id.not_in(existing),
                    )
                )
            ).all()
        )
        for event in events:
            kind = notification_kind(event)
            if kind is None:
                continue
            severity = notification_severity(kind)
            await db.execute(
                insert(EngineeringMissionNotification)
                .values(
                    id=uuid4(),
                    company_id=company_id,
                    event_id=event.id,
                    command_id=event.command_id,
                    kind=kind,
                    severity=severity,
                    status="unread",
                    created_at=event.occurred_at,
                    escalated_at=event.occurred_at if severity == "critical" else None,
                )
                .on_conflict_do_nothing(index_elements=["company_id", "event_id"])
            )
        await db.flush()

    async def _escalate(
        self, db: AsyncSession, *, company_id: UUID, now: datetime
    ) -> None:
        rows = tuple(
            (
                await db.scalars(
                    select(EngineeringMissionNotification)
                    .where(
                        EngineeringMissionNotification.company_id == company_id,
                        EngineeringMissionNotification.status == "unread",
                        EngineeringMissionNotification.escalated_at.is_(None),
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        thresholds = {
            "waiting_for_owner": timedelta(minutes=15),
            "recovering": timedelta(minutes=5),
            "heartbeat_expired": timedelta(minutes=5),
        }
        for record in rows:
            threshold = thresholds.get(record.kind)
            if threshold is not None and record.created_at + threshold <= now:
                record.escalated_at = now
                record.severity = "critical"
                record.version += 1
        await db.flush()


mission_notification_service = MissionNotificationService()
