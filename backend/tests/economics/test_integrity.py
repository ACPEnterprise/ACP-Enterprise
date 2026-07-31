import hashlib
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.economics.allocation import AllocationTarget
from app.economics.contracts import (
    DefineAllocationPolicy,
    EvidenceInput,
    OpenAccountingPeriod,
    RecordBusinessFact,
    TransitionAccountingPeriod,
)
from app.economics.domain import (
    Confidence,
    EconomicCategory,
    EvidenceKind,
    MeasurementStatus,
)
from app.economics.integrity import (
    AccountingPeriodError,
    AccountingPeriodService,
    AllocationExecutionService,
    EconomicsOperationalMetricsService,
    EconomicsReconciliationService,
)
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService
from app.economics.materialization import EconomicsRecalculationService
from app.economics.models import (
    AccountingPeriodHistoryRecord,
    AllocationEvidenceRecord,
    OperationalMetricRecord,
    ProfitabilityProjectionRecord,
)
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch  # noqa: F401
from app.platform.company.models import Company
from app.platform.employees.models import Employee  # noqa: F401
from app.platform.permissions.models import Permission, Role  # noqa: F401
from app.platform.users.models import User  # noqa: F401


@pytest_asyncio.fixture
async def economics_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_period_governed_allocation_reconciliation_and_publication(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    company = Company(
        name="Economics Integrity",
        code=f"ECI{uuid4().hex[:8].upper()}",
        status="active",
        timezone="UTC",
    )
    owner_id, branch_id, job_id = uuid4(), uuid4(), uuid4()
    period_date = date(2026, 7, 31)
    async with economics_database() as session, session.begin():
        session.add(company)
        await session.flush()
        period = await AccountingPeriodService.open_period(
            session,
            company.id,
            OpenAccountingPeriod(
                period_date, period_date, owner_id, "Open July close."
            ),
        )
        event = BusinessEvent(
            event_type="invoice.issued",
            entity_type="job",
            entity_id=job_id,
            company_id=company.id,
            branch_id=branch_id,
            payload={"amount_minor": 100_000, "currency": "USD"},
        )
        session.add(event)
        await session.flush()
        event_evidence = EvidenceInput(
            kind=EvidenceKind.BUSINESS_EVENT,
            reference_id=str(event.id),
            source_system="acp_enterprise",
            source_record_type="business_event",
            source_version="1",
            content_digest=hashlib.sha256(str(event.id).encode()).hexdigest(),
            observed_at=event.occurred_at,
            explanation="Authoritative invoice event.",
            business_event_id=event.id,
        )
        source_evidence = EvidenceInput(
            kind=EvidenceKind.SOURCE_RECORD,
            reference_id="invoice-100",
            source_system="acp_enterprise",
            source_record_type="invoice",
            source_version="1",
            content_digest=hashlib.sha256(b"invoice-100:1").hexdigest(),
            observed_at=event.occurred_at,
            explanation="Authoritative invoice record.",
        )
        fact = await EconomicsLedgerService.record_fact(
            session,
            company.id,
            RecordBusinessFact(
                branch_id=branch_id,
                subject_type="job",
                subject_id=job_id,
                category=EconomicCategory.REVENUE,
                fact_key="invoice_revenue",
                amount_minor=100_000,
                currency="USD",
                confidence=Confidence(
                    MeasurementStatus.MEASURED, 100, "Measured invoice."
                ),
                evidence=(event_evidence, source_evidence),
                occurred_at=event.occurred_at,
                period_start=period_date,
                period_end=period_date,
                measurement_method="invoice_total",
            ),
        )
        policy = await EconomicsLedgerService.define_allocation_policy(
            session,
            company.id,
            DefineAllocationPolicy(
                "revenue-v1", "revenue", "invoice_revenue", "Allocate measured revenue."
            ),
        )
        run = await AllocationExecutionService.execute(
            session,
            company.id,
            policy.id,
            fact.id,
            (AllocationTarget("job", job_id, 1),),
        )
        await EconomicsRecalculationService.process_pending(session)
        results = await EconomicsReconciliationService.reconcile(
            session, company.id, period
        )
        metrics = await EconomicsOperationalMetricsService.capture(session, company.id)

        assert run.version == 1
        assert run.residual_amount_minor == 0
        assert all(item.status == "passed" for item in results)
        assert {item.name for item in metrics} == {
            "pending_recalculations",
            "stale_measurements",
            "incomplete_periods",
        }

        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "closing",
            TransitionAccountingPeriod(owner_id, "Reconciled and ready to close."),
        )
        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "closed",
            TransitionAccountingPeriod(owner_id, "Close approved."),
        )
        with pytest.raises(EconomicsLedgerError, match="controlled reopening"):
            await EconomicsLedgerService.record_fact(
                session,
                company.id,
                RecordBusinessFact(
                    branch_id=branch_id,
                    subject_type="job",
                    subject_id=job_id,
                    category=EconomicCategory.REVENUE,
                    fact_key="late_revenue",
                    amount_minor=1,
                    currency="USD",
                    confidence=Confidence(
                        MeasurementStatus.MEASURED, 100, "Late evidence."
                    ),
                    evidence=(event_evidence,),
                    occurred_at=datetime.now(timezone.utc),
                    period_start=period_date,
                    period_end=period_date,
                    measurement_method="late_event",
                ),
            )
        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "reopened",
            TransitionAccountingPeriod(owner_id, "Approved late evidence correction."),
        )
        with pytest.raises(AccountingPeriodError, match="cannot transition"):
            await AccountingPeriodService.transition(
                session,
                company.id,
                period.id,
                "open",
                TransitionAccountingPeriod(owner_id, "Invalid transition."),
            )

    async with economics_database() as session:
        projection_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ProfitabilityProjectionRecord)
                .where(ProfitabilityProjectionRecord.company_id == company.id)
            )
            or 0
        )
        history_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AccountingPeriodHistoryRecord)
                .where(AccountingPeriodHistoryRecord.period_id == period.id)
            )
            or 0
        )
        evidence_count = int(
            await session.scalar(
                select(func.count())
                .select_from(AllocationEvidenceRecord)
                .where(AllocationEvidenceRecord.run_id == run.id)
            )
            or 0
        )
        metric_names = set(
            (
                await session.scalars(
                    select(OperationalMetricRecord.name).where(
                        OperationalMetricRecord.company_id == company.id
                    )
                )
            ).all()
        )
    assert projection_count == 3
    assert history_count == 4
    assert evidence_count == 2
    assert {
        "allocation_execution_ms",
        "materialization_duration_ms",
        "reconciliation_failures",
    }.issubset(metric_names)
