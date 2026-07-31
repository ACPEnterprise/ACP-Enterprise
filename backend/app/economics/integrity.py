import hashlib
import json
from datetime import date, datetime, timezone
from time import monotonic_ns
from typing import ClassVar
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.allocation import AllocationTarget, allocation_registry
from app.economics.contracts import (
    DefineAllocationPolicy,
    OpenAccountingPeriod,
    TransitionAccountingPeriod,
)
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService
from app.economics.materialization import EconomicsMaterializationService
from app.economics.models import (
    AccountingPeriodHistoryRecord,
    AccountingPeriodRecord,
    AllocationEvidenceRecord,
    AllocationPolicyRecord,
    AllocationRunRecord,
    BusinessFactRecord,
    FactEvidenceRecord,
    OperationalMetricRecord,
    ProfitabilityProjectionRecord,
    ProfitMeasurementRecord,
    RecalculationScopeRecord,
    ReconciliationResultRecord,
)


class AccountingPeriodError(EconomicsLedgerError):
    pass


class AccountingPeriodService:
    _transitions: ClassVar[dict[str, set[str]]] = {
        "open": {"closing"},
        "closing": {"open", "closed"},
        "closed": {"reopened"},
        "reopened": {"closing"},
    }

    @staticmethod
    async def open_period(
        session: AsyncSession, company_id: UUID, command: OpenAccountingPeriod
    ) -> AccountingPeriodRecord:
        if command.period_end < command.period_start or not command.reason.strip():
            raise AccountingPeriodError("a valid period and reason are required")
        overlap = await session.scalar(
            select(AccountingPeriodRecord.id).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.period_start <= command.period_end,
                AccountingPeriodRecord.period_end >= command.period_start,
            )
        )
        if overlap is not None:
            raise AccountingPeriodError("accounting periods cannot overlap")
        period = AccountingPeriodRecord(
            company_id=company_id,
            period_start=command.period_start,
            period_end=command.period_end,
            status="open",
            responsible_owner_id=command.responsible_owner_id,
            reason=command.reason.strip(),
        )
        session.add(period)
        await session.flush()
        session.add(
            AccountingPeriodHistoryRecord(
                company_id=company_id,
                period_id=period.id,
                from_status=None,
                to_status="open",
                responsible_owner_id=command.responsible_owner_id,
                reason=command.reason.strip(),
                version=1,
            )
        )
        await session.flush()
        return period

    @classmethod
    async def transition(
        cls,
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        target_status: str,
        command: TransitionAccountingPeriod,
    ) -> AccountingPeriodRecord:
        period = await session.scalar(
            select(AccountingPeriodRecord)
            .where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
            .with_for_update()
        )
        if period is None:
            raise AccountingPeriodError("accounting period was not found")
        if target_status not in cls._transitions[period.status]:
            raise AccountingPeriodError(
                f"accounting period cannot transition from {period.status} to {target_status}"
            )
        if not command.reason.strip():
            raise AccountingPeriodError("period transition reason is required")
        if target_status == "closed":
            failures = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ReconciliationResultRecord)
                    .where(
                        ReconciliationResultRecord.company_id == company_id,
                        ReconciliationResultRecord.period_id == period.id,
                        ReconciliationResultRecord.status == "failed",
                    )
                )
                or 0
            )
            pending = int(
                await session.scalar(
                    select(func.count())
                    .select_from(RecalculationScopeRecord)
                    .where(
                        RecalculationScopeRecord.company_id == company_id,
                        RecalculationScopeRecord.period_start >= period.period_start,
                        RecalculationScopeRecord.period_end <= period.period_end,
                        RecalculationScopeRecord.processed_at.is_(None),
                    )
                )
                or 0
            )
            if failures or pending:
                raise AccountingPeriodError(
                    "period cannot close with reconciliation failures or pending recalculations"
                )
        previous = period.status
        period.status = target_status
        period.responsible_owner_id = command.responsible_owner_id
        period.reason = command.reason.strip()
        period.version += 1
        period.updated_at = datetime.now(timezone.utc)
        session.add(
            AccountingPeriodHistoryRecord(
                company_id=company_id,
                period_id=period.id,
                from_status=previous,
                to_status=target_status,
                responsible_owner_id=command.responsible_owner_id,
                reason=command.reason.strip(),
                version=period.version,
            )
        )
        await session.flush()
        return period


class AllocationExecutionService:
    @staticmethod
    async def execute(
        session: AsyncSession,
        company_id: UUID,
        policy_id: UUID,
        source_fact_id: UUID,
        targets: tuple[AllocationTarget, ...],
    ) -> AllocationRunRecord:
        started = monotonic_ns()
        policy = await session.scalar(
            select(AllocationPolicyRecord).where(
                AllocationPolicyRecord.company_id == company_id,
                AllocationPolicyRecord.id == policy_id,
            )
        )
        fact_record = await session.scalar(
            select(BusinessFactRecord).where(
                BusinessFactRecord.company_id == company_id,
                BusinessFactRecord.id == source_fact_id,
            )
        )
        if policy is None or fact_record is None:
            raise EconomicsLedgerError("allocation policy or source fact was not found")
        if fact_record.category not in {
            "labor",
            "revenue",
            "truck",
            "equipment",
            "overhead",
        }:
            raise EconomicsLedgerError("source fact category is not allocatable")
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.period_start <= fact_record.period_start,
                AccountingPeriodRecord.period_end >= fact_record.period_end,
            )
        )
        if period is not None and period.status not in {"open", "reopened"}:
            raise AccountingPeriodError(
                "allocations require an open or reopened period"
            )
        fact = await EconomicsMaterializationService._domain_fact(session, fact_record)
        allocations = allocation_registry.allocate(policy.strategy, fact, targets)
        run = await EconomicsLedgerService.record_allocation_run(
            session, company_id, policy, fact, allocations
        )
        if run.period_id is None:
            run.period_id = period.id if period else None
            run.version = int(
                await session.scalar(
                    select(func.count())
                    .select_from(AllocationRunRecord)
                    .where(
                        AllocationRunRecord.company_id == company_id,
                        AllocationRunRecord.policy_id == policy.id,
                    )
                )
                or 1
            )
            run.execution_duration_ms = max(0, (monotonic_ns() - started) // 1_000_000)
            evidence_ids = tuple(
                (
                    await session.scalars(
                        select(FactEvidenceRecord.evidence_id).where(
                            FactEvidenceRecord.company_id == company_id,
                            FactEvidenceRecord.fact_id == source_fact_id,
                        )
                    )
                ).all()
            )
            session.add_all(
                AllocationEvidenceRecord(
                    run_id=run.id, evidence_id=evidence_id, company_id=company_id
                )
                for evidence_id in evidence_ids
            )
            session.add(
                OperationalMetricRecord(
                    company_id=company_id,
                    name="allocation_execution_ms",
                    value=run.execution_duration_ms,
                    labels={"run_id": str(run.id), "policy_id": str(policy.id)},
                )
            )
            await session.flush()
        return run


class ProjectionPublicationService:
    _fields = (
        "revenue_minor",
        "labor_minor",
        "materials_minor",
        "equipment_minor",
        "truck_minor",
        "overhead_minor",
        "gross_profit_minor",
        "net_profit_minor",
    )

    @classmethod
    async def publish(
        cls,
        session: AsyncSession,
        company_id: UUID,
        scope_type: str,
        scope_id: UUID,
        period_start: date,
        period_end: date,
        branch_id: UUID | None = None,
    ) -> ProfitabilityProjectionRecord:
        if scope_type == "job":
            records = tuple(
                (
                    await session.scalars(
                        select(ProfitMeasurementRecord)
                        .where(
                            ProfitMeasurementRecord.company_id == company_id,
                            ProfitMeasurementRecord.subject_type == "job",
                            ProfitMeasurementRecord.subject_id == scope_id,
                            ProfitMeasurementRecord.period_start == period_start,
                            ProfitMeasurementRecord.period_end == period_end,
                        )
                        .order_by(ProfitMeasurementRecord.version.desc())
                        .limit(1)
                    )
                ).all()
            )
        else:
            latest = (
                select(
                    ProfitMeasurementRecord.id,
                    func.row_number()
                    .over(
                        partition_by=ProfitMeasurementRecord.subject_id,
                        order_by=ProfitMeasurementRecord.version.desc(),
                    )
                    .label("rank"),
                )
                .where(
                    ProfitMeasurementRecord.company_id == company_id,
                    ProfitMeasurementRecord.subject_type == "job",
                    ProfitMeasurementRecord.period_start == period_start,
                    ProfitMeasurementRecord.period_end == period_end,
                )
                .subquery()
            )
            statement = (
                select(ProfitMeasurementRecord)
                .join(latest, latest.c.id == ProfitMeasurementRecord.id)
                .where(latest.c.rank == 1)
            )
            if scope_type == "branch":
                statement = statement.where(
                    ProfitMeasurementRecord.branch_id == scope_id
                )
            records = tuple((await session.scalars(statement)).all())
        currencies = {item.currency for item in records}
        complete = (
            bool(records)
            and len(currencies) == 1
            and all(
                getattr(item, field) is not None
                for item in records
                for field in cls._fields
            )
        )
        values = {
            field: sum(int(getattr(item, field)) for item in records)
            if complete
            else None
            for field in cls._fields
        }
        ids = sorted(str(item.id) for item in records)
        digest = hashlib.sha256(
            json.dumps(
                {"scope": scope_type, "id": str(scope_id), "inputs": ids},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        existing = await session.scalar(
            select(ProfitabilityProjectionRecord).where(
                ProfitabilityProjectionRecord.company_id == company_id,
                ProfitabilityProjectionRecord.input_digest == digest,
            )
        )
        if existing is not None:
            return existing
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.max(ProfitabilityProjectionRecord.version), 0
                        )
                    ).where(
                        ProfitabilityProjectionRecord.company_id == company_id,
                        ProfitabilityProjectionRecord.scope_type == scope_type,
                        ProfitabilityProjectionRecord.scope_id == scope_id,
                        ProfitabilityProjectionRecord.period_start == period_start,
                        ProfitabilityProjectionRecord.period_end == period_end,
                    )
                )
                or 0
            )
            + 1
        )
        projection = ProfitabilityProjectionRecord(
            company_id=company_id,
            branch_id=branch_id,
            scope_type=scope_type,
            scope_id=scope_id,
            period_start=period_start,
            period_end=period_end,
            currency=next(iter(currencies)) if len(currencies) == 1 else None,
            measurement_count=len(records),
            values=values,
            confidence_status="measured" if complete else "unknown",
            confidence_percentage=min(
                (item.confidence_percentage for item in records), default=0
            )
            if complete
            else 0,
            input_measurement_ids=ids,
            input_digest=digest,
            version=version,
        )
        session.add(projection)
        await session.flush()
        return projection


class EconomicsReconciliationService:
    @staticmethod
    async def reconcile(
        session: AsyncSession, company_id: UUID, period: AccountingPeriodRecord
    ) -> tuple[ReconciliationResultRecord, ...]:
        facts = tuple(
            (
                await session.scalars(
                    select(BusinessFactRecord).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                    )
                )
            ).all()
        )
        fact_ids = [item.id for item in facts]
        evidence_count = (
            int(
                await session.scalar(
                    select(func.count(func.distinct(FactEvidenceRecord.fact_id))).where(
                        FactEvidenceRecord.company_id == company_id,
                        FactEvidenceRecord.fact_id.in_(fact_ids),
                    )
                )
                or 0
            )
            if fact_ids
            else 0
        )
        runs = tuple(
            (
                await session.scalars(
                    select(AllocationRunRecord).where(
                        AllocationRunRecord.company_id == company_id,
                        AllocationRunRecord.period_id == period.id,
                    )
                )
            ).all()
        )
        measurements = int(
            await session.scalar(
                select(func.count())
                .select_from(ProfitMeasurementRecord)
                .where(
                    ProfitMeasurementRecord.company_id == company_id,
                    ProfitMeasurementRecord.period_start >= period.period_start,
                    ProfitMeasurementRecord.period_end <= period.period_end,
                )
            )
            or 0
        )
        source_records = sum(
            1
            for item in facts
            if any(e.get("kind") == "source_record" for e in item.evidence_snapshot)
        )
        checks: tuple[tuple[str, int, int, int, dict[str, object]], ...] = (
            (
                "source",
                len(facts),
                source_records,
                0,
                {"missing": len(facts) - source_records},
            ),
            ("ledger", len(facts), len(set(fact_ids)), 0, {}),
            (
                "allocation",
                len(runs),
                sum(1 for item in runs if item.residual_amount_minor == 0),
                sum(item.residual_amount_minor for item in runs),
                {},
            ),
            (
                "measurement",
                len({item.subject_id for item in facts if item.subject_type == "job"}),
                measurements,
                0,
                {},
            ),
            (
                "evidence",
                len(facts),
                evidence_count,
                0,
                {"missing": len(facts) - evidence_count},
            ),
        )
        output = []
        for kind, expected, actual, variance, details in checks:
            digest = hashlib.sha256(
                f"{period.id}:{period.version}:{kind}:{expected}:{actual}:{variance}".encode()
            ).hexdigest()
            existing = await session.scalar(
                select(ReconciliationResultRecord).where(
                    ReconciliationResultRecord.company_id == company_id,
                    ReconciliationResultRecord.input_digest == digest,
                )
            )
            result = existing or ReconciliationResultRecord(
                company_id=company_id,
                period_id=period.id,
                kind=kind,
                status="passed" if expected == actual and variance == 0 else "failed",
                expected_count=expected,
                actual_count=actual,
                variance_minor=variance,
                details=details,
                input_digest=digest,
            )
            if existing is None:
                session.add(result)
            output.append(result)
        failures = sum(item.status == "failed" for item in output)
        session.add(
            OperationalMetricRecord(
                company_id=company_id,
                name="reconciliation_failures",
                value=failures,
                labels={"period_id": str(period.id)},
            )
        )
        await session.flush()
        return tuple(output)


class EconomicsOperationalMetricsService:
    @staticmethod
    async def capture(
        session: AsyncSession, company_id: UUID
    ) -> tuple[OperationalMetricRecord, ...]:
        stale = ProfitMeasurementRecord.__table__.alias("measurement")
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(RecalculationScopeRecord)
                .where(
                    RecalculationScopeRecord.company_id == company_id,
                    RecalculationScopeRecord.processed_at.is_(None),
                )
            )
            or 0
        )
        stale_count = int(
            await session.scalar(
                select(func.count())
                .select_from(stale)
                .where(
                    stale.c.company_id == company_id,
                    exists(
                        select(1).where(
                            RecalculationScopeRecord.company_id == company_id,
                            RecalculationScopeRecord.scope_type == stale.c.subject_type,
                            RecalculationScopeRecord.scope_id == stale.c.subject_id,
                            RecalculationScopeRecord.requested_at > stale.c.measured_at,
                        )
                    ),
                )
            )
            or 0
        )
        incomplete = int(
            await session.scalar(
                select(func.count())
                .select_from(AccountingPeriodRecord)
                .where(
                    AccountingPeriodRecord.company_id == company_id,
                    AccountingPeriodRecord.status.in_(("open", "closing", "reopened")),
                )
            )
            or 0
        )
        counts = {
            "pending_recalculations": pending,
            "stale_measurements": stale_count,
            "incomplete_periods": incomplete,
        }
        records = tuple(
            OperationalMetricRecord(
                company_id=company_id, name=name, value=value, labels={}
            )
            for name, value in counts.items()
        )
        session.add_all(records)
        await session.flush()
        return records


async def define_policy(
    session: AsyncSession, company_id: UUID, command: DefineAllocationPolicy
) -> AllocationPolicyRecord:
    return await EconomicsLedgerService.define_allocation_policy(
        session, company_id, command
    )
