import hashlib
from datetime import datetime, timedelta, timezone
from time import monotonic_ns
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.accounting import (
    FinancialCloseService,
    GeneralLedgerReconciliationService,
    PeriodAuditPackageService,
)
from app.economics.allocation import AllocationTarget
from app.economics.integrity import (
    AllocationExecutionService,
    EconomicsOperationalMetricsService,
    EconomicsReconciliationService,
)
from app.economics.materialization import EconomicsRecalculationService
from app.economics.models import (
    AccountingPeriodRecord,
    EconomicsProcessingWorkItem,
    OperationalMetricRecord,
)


class EconomicsProcessingError(RuntimeError):
    pass


class EconomicsScheduledProcessingService:
    @classmethod
    async def enqueue_period_pipeline(
        cls,
        session: AsyncSession,
        *,
        company_id: UUID,
        period_id: UUID,
        responsible_owner_id: UUID,
    ) -> tuple[EconomicsProcessingWorkItem, ...]:
        stages = (
            "recalculation",
            "materialization",
            "publication",
            "reconciliation",
            "monitoring",
        )
        return tuple(
            [
                await cls.enqueue(
                    session,
                    company_id=company_id,
                    period_id=period_id,
                    kind=stage,
                    scope_type="period",
                    scope_id=period_id,
                    idempotency_key=f"period:{period_id}:{stage}",
                    payload={"responsible_owner_id": str(responsible_owner_id)},
                )
                for stage in stages
            ]
        )

    @staticmethod
    async def enqueue(
        session: AsyncSession,
        *,
        company_id: UUID,
        kind: str,
        scope_type: str,
        scope_id: UUID,
        idempotency_key: str,
        period_id: UUID | None = None,
        payload: dict[str, object] | None = None,
        max_attempts: int = 5,
    ) -> EconomicsProcessingWorkItem:
        existing = await session.scalar(
            select(EconomicsProcessingWorkItem).where(
                EconomicsProcessingWorkItem.company_id == company_id,
                EconomicsProcessingWorkItem.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        if max_attempts < 1:
            raise EconomicsProcessingError("processing max attempts must be positive")
        item = EconomicsProcessingWorkItem(
            company_id=company_id,
            period_id=period_id,
            kind=kind,
            scope_type=scope_type,
            scope_id=scope_id,
            payload=payload or {},
            idempotency_key=idempotency_key,
            status="pending",
            max_attempts=max_attempts,
        )
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def recover_abandoned(
        session: AsyncSession,
        *,
        now: datetime | None = None,
        claim_timeout: timedelta = timedelta(minutes=10),
    ) -> int:
        current = now or datetime.now(timezone.utc)
        records = tuple(
            (
                await session.scalars(
                    select(EconomicsProcessingWorkItem)
                    .where(
                        EconomicsProcessingWorkItem.status == "processing",
                        EconomicsProcessingWorkItem.claimed_at
                        < current - claim_timeout,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for item in records:
            item.status = (
                "retry_scheduled"
                if item.attempt_count < item.max_attempts
                else "failed"
            )
            item.available_at = current
            item.claimed_at = None
            item.last_error = "Recovered after interrupted processing claim."
            item.failure_evidence_digest = hashlib.sha256(
                f"{item.id}:{item.attempt_count}:restart_recovery".encode()
            ).hexdigest()
            item.updated_at = current
        await session.flush()
        return len(records)

    @classmethod
    async def process_next(
        cls, session: AsyncSession, *, now: datetime | None = None
    ) -> EconomicsProcessingWorkItem | None:
        current = now or datetime.now(timezone.utc)
        item = await session.scalar(
            select(EconomicsProcessingWorkItem)
            .where(
                EconomicsProcessingWorkItem.status.in_(("pending", "retry_scheduled")),
                EconomicsProcessingWorkItem.available_at <= current,
            )
            .order_by(
                EconomicsProcessingWorkItem.available_at,
                EconomicsProcessingWorkItem.created_at,
                EconomicsProcessingWorkItem.id,
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if item is None:
            return None
        item.status = "processing"
        item.claimed_at = current
        item.attempt_count += 1
        item.updated_at = current
        await session.flush()
        started = monotonic_ns()
        try:
            async with session.begin_nested():
                await cls._dispatch(session, item)
        except Exception as error:  # noqa: BLE001 - durable queue records all failures
            message = f"{type(error).__name__}: {error}"[:2000]
            item.status = (
                "retry_scheduled"
                if item.attempt_count < item.max_attempts
                else "failed"
            )
            item.available_at = current + timedelta(
                seconds=min(300, 2**item.attempt_count)
            )
            item.claimed_at = None
            item.last_error = message
            item.failure_evidence_digest = hashlib.sha256(
                f"{item.id}:{item.attempt_count}:{message}".encode()
            ).hexdigest()
            session.add(
                OperationalMetricRecord(
                    company_id=item.company_id,
                    name="scheduled_processing_failures",
                    value=1,
                    labels={"kind": item.kind, "work_item_id": str(item.id)},
                )
            )
        else:
            item.status = "completed"
            item.completed_at = current
            item.claimed_at = None
            item.last_error = None
            item.failure_evidence_digest = None
        item.updated_at = current
        session.add(
            OperationalMetricRecord(
                company_id=item.company_id,
                name="scheduled_processing_duration_ms",
                value=max(0, (monotonic_ns() - started) // 1_000_000),
                labels={
                    "kind": item.kind,
                    "status": item.status,
                    "work_item_id": str(item.id),
                },
            )
        )
        await session.flush()
        return item

    @staticmethod
    async def _period(
        session: AsyncSession, item: EconomicsProcessingWorkItem
    ) -> AccountingPeriodRecord:
        if item.period_id is None:
            raise EconomicsProcessingError(
                "processing item requires an accounting period"
            )
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == item.company_id,
                AccountingPeriodRecord.id == item.period_id,
            )
        )
        if period is None:
            raise EconomicsProcessingError("processing accounting period was not found")
        return period

    @classmethod
    async def _dispatch(
        cls, session: AsyncSession, item: EconomicsProcessingWorkItem
    ) -> None:
        if item.kind in {"recalculation", "materialization", "publication"}:
            await EconomicsRecalculationService.process_pending(session)
            return
        if item.kind == "allocation":
            policy_id = UUID(str(item.payload["policy_id"]))
            source_fact_id = UUID(str(item.payload["source_fact_id"]))
            raw_targets = item.payload.get("targets")
            if not isinstance(raw_targets, list):
                raise EconomicsProcessingError("allocation targets are required")
            targets = tuple(
                AllocationTarget(
                    subject_type=str(target["subject_type"]),
                    subject_id=UUID(str(target["subject_id"])),
                    weight=int(target["weight"]),
                )
                for target in raw_targets
                if isinstance(target, dict)
            )
            await AllocationExecutionService.execute(
                session, item.company_id, policy_id, source_fact_id, targets
            )
            return
        if item.kind == "reconciliation":
            period = await cls._period(session, item)
            await EconomicsReconciliationService.reconcile(
                session, item.company_id, period
            )
            await GeneralLedgerReconciliationService.reconcile(
                session, item.company_id, period.id
            )
            owner_id = UUID(
                str(
                    item.payload.get(
                        "responsible_owner_id", period.responsible_owner_id
                    )
                )
            )
            await FinancialCloseService.evaluate_readiness(
                session, item.company_id, period.id, owner_id
            )
            await PeriodAuditPackageService.build(session, item.company_id, period.id)
            return
        if item.kind == "monitoring":
            await EconomicsOperationalMetricsService.capture(session, item.company_id)
            return
        raise EconomicsProcessingError(f"unsupported processing kind: {item.kind}")
