from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    String,
    UniqueConstraint,
    case,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.engineering_control.mobile.control import EngineeringWorkstreamControl
from app.worker_control.contracts import AuthenticatedWorkerContext

ACK_TTL = timedelta(minutes=5)
RUNTIME_STATES = (
    "queued",
    "acknowledged",
    "running",
    "paused",
    "waiting_for_owner",
    "validating",
    "deploying_preview",
    "completed",
    "failed",
    "cancelled",
    "recovering",
)


class EngineeringWorkstreamRuntime(Base):
    __tablename__ = "engineering_workstream_runtimes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id", "worker_id"],
            ["engineering_workers.company_id", "engineering_workers.id"],
            name="fk_workstream_runtime_worker",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "runtime_state IN " + str(RUNTIME_STATES),
            name="ck_workstream_runtime_state",
        ),
        CheckConstraint(
            "version >= 1 AND acknowledged_control_version >= 1",
            name="ck_workstream_runtime_versions",
        ),
        CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="ck_workstream_runtime_progress",
        ),
        UniqueConstraint(
            "company_id", "command_id", name="uq_workstream_runtime_command"
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
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    control_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    worker_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    acknowledged_control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    acknowledged_action: Mapped[str] = mapped_column(String(16), nullable=False)
    runtime_state: Mapped[str] = mapped_column(String(32), nullable=False)
    worker_health: Mapped[str] = mapped_column(String(24), nullable=False)
    progress_percent: Mapped[int | None] = mapped_column(Integer)
    current_activity: Mapped[str | None] = mapped_column(String(240))
    reason_code: Mapped[str | None] = mapped_column(String(100))
    acknowledged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    acknowledgement_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class EngineeringWorkstreamEvent(Base):
    __tablename__ = "engineering_workstream_events"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "idempotency_key", name="uq_workstream_event_idempotency"
        ),
        Index(
            "ix_workstream_events_company_order",
            "company_id",
            "sequence_id",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    sequence_id: Mapped[int] = mapped_column(
        BigInteger, Identity(), nullable=False, unique=True
    )
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("engineering_commands.id", ondelete="RESTRICT"),
        nullable=False,
    )
    control_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    control_version: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    worker_session_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    runtime_state: Mapped[str | None] = mapped_column(String(32))
    reason_code: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class WorkstreamRuntimeError(Exception):
    pass


class WorkstreamRuntimeService:
    async def converge_adopted_owner_review(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        result_id: UUID,
        review_id: UUID,
        now: datetime,
    ) -> EngineeringWorkstreamRuntime:
        """Append an audited terminal projection without rewriting an expired ack."""
        idempotency_key = f"adopted-owner-review:{result_id}:{review_id}"
        runtime = await db.scalar(
            select(EngineeringWorkstreamRuntime)
            .where(
                EngineeringWorkstreamRuntime.company_id == company_id,
                EngineeringWorkstreamRuntime.command_id == command_id,
            )
            .with_for_update()
        )
        if runtime is None:
            raise WorkstreamRuntimeError("Workstream runtime projection was not found.")
        duplicate = await db.scalar(
            select(EngineeringWorkstreamEvent.id).where(
                EngineeringWorkstreamEvent.company_id == company_id,
                EngineeringWorkstreamEvent.idempotency_key == idempotency_key,
            )
        )
        target_reason = (
            "heartbeat_expired"
            if runtime.worker_health == "unhealthy"
            and runtime.reason_code == "heartbeat_expired"
            else "adopted_result_owner_review"
        )
        projection_drifted = (
            runtime.runtime_state != "waiting_for_owner"
            or runtime.progress_percent != 100
            or runtime.current_activity != "Published result ready for owner review"
            or runtime.reason_code != target_reason
        )
        if projection_drifted:
            runtime.runtime_state = "waiting_for_owner"
            runtime.progress_percent = 100
            runtime.current_activity = "Published result ready for owner review"
            runtime.reason_code = target_reason
            runtime.updated_at = now
            runtime.version += 1
        if duplicate is not None:
            await db.flush()
            return runtime
        db.add(
            EngineeringWorkstreamEvent(
                company_id=company_id,
                command_id=command_id,
                control_id=runtime.control_id,
                control_version=runtime.acknowledged_control_version,
                worker_id=runtime.worker_id,
                worker_session_id=runtime.worker_session_id,
                event_type="result_reconciliation",
                action=runtime.acknowledged_action,
                runtime_state="waiting_for_owner",
                reason_code="adopted_result_owner_review",
                idempotency_key=idempotency_key,
                occurred_at=now,
            )
        )
        await db.flush()
        return runtime

    async def project_provider_progress(
        self,
        db: AsyncSession,
        *,
        company_id: UUID,
        command_id: UUID,
        attempt_id: UUID,
        sequence_number: int,
        phase: str,
        percentage: int | None,
        summary: str | None,
        message_code: str,
        occurred_at: datetime,
    ) -> EngineeringWorkstreamRuntime | None:
        """Project durable provider truth into the phone-owned runtime projection."""
        runtime = await db.scalar(
            select(EngineeringWorkstreamRuntime)
            .where(
                EngineeringWorkstreamRuntime.company_id == company_id,
                EngineeringWorkstreamRuntime.command_id == command_id,
            )
            .with_for_update()
        )
        if runtime is None:
            return None
        idempotency_key = f"provider-progress:{attempt_id}:{sequence_number}"
        duplicate = await db.scalar(
            select(EngineeringWorkstreamEvent.id).where(
                EngineeringWorkstreamEvent.company_id == company_id,
                EngineeringWorkstreamEvent.idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            return runtime
        phase_floor = {
            "preparing": 5,
            "starting": 10,
            "executing": 25,
            "validating": 80,
            "finalizing": 95,
        }.get(phase, 0)
        projected = max(phase_floor, percentage or 0)
        runtime.progress_percent = max(runtime.progress_percent or 0, projected)
        runtime.runtime_state = "validating" if phase == "validating" else "running"
        runtime.current_activity = (summary or message_code.replace("_", " "))[:240]
        runtime.updated_at = occurred_at
        runtime.version += 1
        db.add(
            EngineeringWorkstreamEvent(
                company_id=company_id,
                command_id=command_id,
                control_id=runtime.control_id,
                control_version=runtime.acknowledged_control_version,
                worker_id=runtime.worker_id,
                worker_session_id=runtime.worker_session_id,
                event_type="provider_progress",
                action=runtime.acknowledged_action,
                runtime_state=runtime.runtime_state,
                reason_code=message_code,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
            )
        )
        await db.flush()
        return runtime

    async def refresh_attached_heartbeats(
        self,
        db: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        health: str,
        now: datetime,
    ) -> int:
        """Keep controls acknowledged by this exact authenticated session alive."""
        result = await db.execute(
            update(EngineeringWorkstreamRuntime)
            .where(
                EngineeringWorkstreamRuntime.company_id == context.company_id,
                EngineeringWorkstreamRuntime.worker_id == context.worker_id,
                EngineeringWorkstreamRuntime.worker_session_id == session_id,
                EngineeringWorkstreamRuntime.runtime_state.notin_(
                    {"completed", "failed", "cancelled", "recovering"}
                ),
            )
            .values(
                worker_health=health,
                heartbeat_at=now,
                acknowledgement_expires_at=now + ACK_TTL,
                reason_code=case(
                    (
                        EngineeringWorkstreamRuntime.reason_code == "heartbeat_expired",
                        None,
                    ),
                    else_=EngineeringWorkstreamRuntime.reason_code,
                ),
                updated_at=now,
            )
        )
        return int(getattr(result, "rowcount", 0))

    async def pending(
        self,
        db: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID | None = None,
        now: datetime | None = None,
    ) -> tuple[EngineeringWorkstreamControl, ...]:
        checked = now or datetime.now(timezone.utc)
        rows = await db.scalars(
            select(EngineeringWorkstreamControl)
            .outerjoin(
                EngineeringWorkstreamRuntime,
                (
                    EngineeringWorkstreamRuntime.company_id
                    == EngineeringWorkstreamControl.company_id
                )
                & (
                    EngineeringWorkstreamRuntime.command_id
                    == EngineeringWorkstreamControl.command_id
                ),
            )
            .where(
                EngineeringWorkstreamControl.company_id == context.company_id,
                or_(
                    EngineeringWorkstreamRuntime.id.is_(None),
                    EngineeringWorkstreamRuntime.acknowledged_control_version
                    < EngineeringWorkstreamControl.version,
                    EngineeringWorkstreamRuntime.acknowledgement_expires_at <= checked,
                    *(
                        (EngineeringWorkstreamRuntime.worker_session_id != session_id,)
                        if session_id is not None
                        else ()
                    ),
                ),
            )
            .order_by(
                EngineeringWorkstreamControl.updated_at, EngineeringWorkstreamControl.id
            )
            .limit(10)
        )
        return tuple(rows)

    async def acknowledge(
        self,
        db: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        control_id: UUID,
        expected_control_version: int,
        action: str,
        idempotency_key: str,
        reason_code: str | None,
        now: datetime,
    ) -> EngineeringWorkstreamRuntime:
        duplicate = await db.scalar(
            select(EngineeringWorkstreamEvent).where(
                EngineeringWorkstreamEvent.company_id == context.company_id,
                EngineeringWorkstreamEvent.idempotency_key == idempotency_key,
            )
        )
        if duplicate is not None:
            runtime = await db.scalar(
                select(EngineeringWorkstreamRuntime).where(
                    EngineeringWorkstreamRuntime.company_id == context.company_id,
                    EngineeringWorkstreamRuntime.command_id == duplicate.command_id,
                )
            )
            if runtime is None:
                raise WorkstreamRuntimeError(
                    "Duplicate acknowledgement has no runtime projection."
                )
            return runtime
        control = await db.scalar(
            select(EngineeringWorkstreamControl)
            .where(
                EngineeringWorkstreamControl.company_id == context.company_id,
                EngineeringWorkstreamControl.id == control_id,
            )
            .with_for_update()
        )
        if control is None:
            raise WorkstreamRuntimeError("Workstream control was not found.")
        if (
            control.version != expected_control_version
            or control.requested_action != action
        ):
            raise WorkstreamRuntimeError("Owner request is stale.")
        runtime = await db.scalar(
            select(EngineeringWorkstreamRuntime)
            .where(
                EngineeringWorkstreamRuntime.company_id == context.company_id,
                EngineeringWorkstreamRuntime.command_id == control.command_id,
            )
            .with_for_update()
        )
        state = {"pause": "paused", "cancel": "cancelled"}.get(action, "acknowledged")
        if runtime is None:
            runtime = EngineeringWorkstreamRuntime(
                company_id=context.company_id,
                command_id=control.command_id,
                control_id=control.id,
                worker_id=context.worker_id,
                worker_session_id=session_id,
                acknowledged_control_version=control.version,
                acknowledged_action=action,
                runtime_state=state,
                worker_health="healthy",
                acknowledged_at=now,
                acknowledgement_expires_at=now + ACK_TTL,
                heartbeat_at=now,
                updated_at=now,
            )
            db.add(runtime)
        else:
            if runtime.acknowledged_control_version > control.version:
                raise WorkstreamRuntimeError("Owner request is stale.")
            ambiguous_interruption = runtime.runtime_state == "recovering" and (
                runtime.progress_percent is not None
                or runtime.current_activity is not None
            )
            runtime.control_id = control.id
            runtime.worker_id = context.worker_id
            runtime.worker_session_id = session_id
            runtime.acknowledged_control_version = control.version
            runtime.acknowledged_action = action
            runtime.runtime_state = (
                "waiting_for_owner" if ambiguous_interruption else state
            )
            runtime.worker_health = "healthy"
            runtime.reason_code = (
                "reconciliation_required" if ambiguous_interruption else reason_code
            )
            runtime.acknowledged_at = now
            runtime.acknowledgement_expires_at = now + ACK_TTL
            runtime.heartbeat_at = now
            runtime.updated_at = now
            runtime.version += 1
        db.add(
            EngineeringWorkstreamEvent(
                company_id=context.company_id,
                command_id=control.command_id,
                control_id=control.id,
                control_version=control.version,
                worker_id=context.worker_id,
                worker_session_id=session_id,
                event_type="worker_acknowledgement",
                action=action,
                runtime_state=state,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
                occurred_at=now,
            )
        )
        await db.flush()
        return runtime

    async def transition(
        self,
        db: AsyncSession,
        *,
        context: AuthenticatedWorkerContext,
        session_id: UUID,
        command_id: UUID,
        expected_version: int,
        runtime_state: str,
        health: str,
        progress_percent: int | None,
        current_activity: str | None,
        reason_code: str | None,
        idempotency_key: str,
        now: datetime,
    ) -> EngineeringWorkstreamRuntime:
        if runtime_state not in RUNTIME_STATES:
            raise WorkstreamRuntimeError("Runtime state is invalid.")
        duplicate = await db.scalar(
            select(EngineeringWorkstreamEvent).where(
                EngineeringWorkstreamEvent.company_id == context.company_id,
                EngineeringWorkstreamEvent.idempotency_key == idempotency_key,
            )
        )
        runtime = await db.scalar(
            select(EngineeringWorkstreamRuntime)
            .where(
                EngineeringWorkstreamRuntime.company_id == context.company_id,
                EngineeringWorkstreamRuntime.command_id == command_id,
            )
            .with_for_update()
        )
        if runtime is None:
            raise WorkstreamRuntimeError("Workstream was not acknowledged.")
        if duplicate is not None:
            return runtime
        if runtime.version != expected_version:
            raise WorkstreamRuntimeError("Runtime version is stale.")
        if runtime.worker_id != context.worker_id:
            raise WorkstreamRuntimeError("Workstream belongs to another worker.")
        if runtime.acknowledgement_expires_at <= now and runtime_state not in {
            "recovering",
            "cancelled",
            "failed",
        }:
            raise WorkstreamRuntimeError(
                "Worker acknowledgement expired; recovery is required."
            )
        runtime.worker_session_id = session_id
        runtime.runtime_state = runtime_state
        runtime.worker_health = health
        runtime.progress_percent = progress_percent
        runtime.current_activity = current_activity
        runtime.reason_code = reason_code
        runtime.heartbeat_at = now
        runtime.updated_at = now
        runtime.acknowledgement_expires_at = now + ACK_TTL
        runtime.version += 1
        db.add(
            EngineeringWorkstreamEvent(
                company_id=context.company_id,
                command_id=command_id,
                control_id=runtime.control_id,
                control_version=runtime.acknowledged_control_version,
                worker_id=context.worker_id,
                worker_session_id=session_id,
                event_type="runtime_transition",
                action=runtime.acknowledged_action,
                runtime_state=runtime_state,
                reason_code=reason_code,
                idempotency_key=idempotency_key,
                occurred_at=now,
            )
        )
        await db.flush()
        return runtime


workstream_runtime_service = WorkstreamRuntimeService()
