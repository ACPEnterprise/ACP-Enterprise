import hashlib
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.economics.accounting import (
    AccountingContractService,
    ChartMapping,
    ExportAcknowledgement,
    FinancialCloseService,
    FinancialIntegrityPublicationService,
    GeneralLedgerReconciliationService,
    JournalExport,
    JournalLine,
    PeriodAuditPackageService,
    SourceBindingService,
)
from app.economics.contracts import (
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
    AccountingPeriodService,
    EconomicsReconciliationService,
)
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService
from app.economics.materialization import EconomicsRecalculationService
from app.economics.models import (
    AccountingPeriodHistoryRecord,
    BusinessFactRecord,
    EconomicsProcessingWorkItem,
    FinancialIntegrityPublicationRecord,
    ProfitabilityProjectionRecord,
)
from app.economics.phase4_service import (
    EconomicsPhase4NotFoundError,
    EconomicsPhase4QueryService,
)
from app.economics.processing import EconomicsScheduledProcessingService
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


async def _fact(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    job_id: UUID,
    period_date: date,
    category: EconomicCategory,
    amount: int,
    correction_kind: str = "original",
    corrects_fact_id: UUID | None = None,
) -> BusinessFactRecord:
    event = BusinessEvent(
        event_type=f"economics.{category.value}.measured",
        entity_type="job",
        entity_id=job_id,
        company_id=company_id,
        branch_id=branch_id,
        payload={"amount_minor": amount, "currency": "USD"},
    )
    session.add(event)
    await session.flush()
    evidence = (
        EvidenceInput(
            kind=EvidenceKind.SOURCE_RECORD,
            reference_id=f"{category.value}-{job_id}-{amount}",
            source_system="acp_enterprise",
            source_record_type=f"{category.value}_source",
            source_version=str(amount),
            content_digest=hashlib.sha256(
                f"source:{category}:{amount}".encode()
            ).hexdigest(),
            observed_at=event.occurred_at,
            explanation="Authoritative operational source record.",
        ),
        EvidenceInput(
            kind=EvidenceKind.BUSINESS_EVENT,
            reference_id=str(event.id),
            source_system="acp_enterprise",
            source_record_type="business_event",
            source_version="1",
            content_digest=hashlib.sha256(
                f"event:{event.id}:{amount}".encode()
            ).hexdigest(),
            observed_at=event.occurred_at,
            explanation="Authoritative source event.",
            business_event_id=event.id,
        ),
    )
    return await EconomicsLedgerService.record_fact(
        session,
        company_id,
        RecordBusinessFact(
            branch_id=branch_id,
            subject_type="job",
            subject_id=job_id,
            category=category,
            fact_key=category.value,
            amount_minor=amount,
            currency="USD",
            confidence=Confidence(MeasurementStatus.MEASURED, 100, "Measured source."),
            evidence=evidence,
            occurred_at=event.occurred_at,
            period_start=period_date,
            period_end=period_date,
            measurement_method="authoritative_source_amount",
            correction_kind=correction_kind,
            corrects_fact_id=corrects_fact_id,
        ),
    )


@pytest.mark.asyncio
async def test_financial_close_export_audit_publication_and_reopening(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    company = Company(
        name="Phase 4 Economics",
        code=f"P4{uuid4().hex[:8].upper()}",
        status="active",
        timezone="UTC",
    )
    owner_id, branch_id, job_id = uuid4(), uuid4(), uuid4()
    period_date = date(2026, 8, 1)
    async with economics_database() as session, session.begin():
        session.add(company)
        await session.flush()
        bindings = await SourceBindingService.bind_available_sources(
            session, company.id
        )
        assert len(bindings) == 10
        assert {item.status for item in bindings} == {
            "bound",
            "read_only",
            "contract_ready",
        }
        mapping_v1 = await AccountingContractService.define_mapping(
            session,
            company.id,
            ChartMapping(
                "service-revenue",
                "revenue",
                "4000",
                "Provider-neutral service revenue classification.",
                branch_dimension_key="branch",
            ),
        )
        mapping_v2 = await AccountingContractService.define_mapping(
            session,
            company.id,
            ChartMapping(
                "service-revenue",
                "revenue",
                "4010",
                "Versioned chart update without provider coupling.",
                branch_dimension_key="branch",
            ),
        )
        assert (mapping_v1.version, mapping_v2.version) == (1, 2)
        period = await AccountingPeriodService.open_period(
            session,
            company.id,
            OpenAccountingPeriod(period_date, period_date, owner_id, "August close."),
        )
        amounts = {
            EconomicCategory.REVENUE: 100_000,
            EconomicCategory.LABOR: 20_000,
            EconomicCategory.MATERIALS: 15_000,
            EconomicCategory.EQUIPMENT: 5_000,
            EconomicCategory.TRUCK: 2_000,
            EconomicCategory.OVERHEAD: 10_000,
        }
        facts = {
            category: await _fact(
                session,
                company_id=company.id,
                branch_id=branch_id,
                job_id=job_id,
                period_date=period_date,
                category=category,
                amount=amount,
            )
            for category, amount in amounts.items()
        }
        await EconomicsRecalculationService.process_pending(session)
        projection = await session.scalar(
            select(ProfitabilityProjectionRecord).where(
                ProfitabilityProjectionRecord.company_id == company.id,
                ProfitabilityProjectionRecord.scope_type == "company",
                ProfitabilityProjectionRecord.scope_id == company.id,
            )
        )
        assert projection is not None
        total_source = sum(amounts.values())
        line_digest = "a" * 64
        export_command = JournalExport(
            export_key="august-close",
            currency="USD",
            lines=(
                JournalLine(
                    "ECON-CLEARING", "debit", total_source, "period-source", line_digest
                ),
                JournalLine(
                    "ECON-OFFSET", "credit", total_source, "period-source", line_digest
                ),
            ),
            source_projection_ids=(projection.id,),
        )
        export = await AccountingContractService.prepare_export(
            session, company.id, period.id, export_command
        )
        replay = await AccountingContractService.prepare_export(
            session, company.id, period.id, export_command
        )
        assert replay.id == export.id
        await AccountingContractService.mark_exported(
            session, company.id, export.id, export.checksum
        )
        await AccountingContractService.acknowledge_export(
            session,
            company.id,
            export.id,
            ExportAcknowledgement(True, "ledger-ack-1"),
        )
        correction_command = JournalExport(
            export_key="august-close",
            currency="USD",
            lines=(
                JournalLine(
                    "ECON-CLEARING-V2", "debit", total_source, "period-source", "b" * 64
                ),
                JournalLine(
                    "ECON-OFFSET-V2", "credit", total_source, "period-source", "b" * 64
                ),
            ),
            source_projection_ids=(projection.id,),
            corrects_export_id=export.id,
        )
        correction_export = await AccountingContractService.prepare_export(
            session, company.id, period.id, correction_command
        )
        correction_replay = await AccountingContractService.prepare_export(
            session, company.id, period.id, correction_command
        )
        assert correction_replay.id == correction_export.id
        await AccountingContractService.mark_exported(
            session, company.id, correction_export.id, correction_export.checksum
        )
        await AccountingContractService.acknowledge_export(
            session,
            company.id,
            correction_export.id,
            ExportAcknowledgement(True, "ledger-ack-2"),
        )
        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "closing",
            TransitionAccountingPeriod(owner_id, "Freeze inputs for reconciliation."),
        )
        results = await EconomicsReconciliationService.reconcile(
            session, company.id, period
        )
        gl = await GeneralLedgerReconciliationService.reconcile(
            session, company.id, period.id
        )
        readiness = await FinancialCloseService.evaluate_readiness(
            session, company.id, period.id, owner_id
        )
        package = await PeriodAuditPackageService.build(session, company.id, period.id)
        publication = await FinancialIntegrityPublicationService.publish(
            session, company.id, period.id, projection.id
        )
        assert all(item.status == "passed" for item in results)
        assert gl.status == "passed"
        assert gl.period_variance_minor == 0
        assert readiness.ready
        assert not readiness.blockers
        assert len(package.package_digest) == 64
        assert package.manifest["measurement_confidence"]
        assert package.manifest["facts_detail"]
        assert publication.integrity_status == "reconciled"
        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "closed",
            TransitionAccountingPeriod(owner_id, "Close evidence approved."),
        )
        with pytest.raises(EconomicsLedgerError, match="controlled reopening"):
            await _fact(
                session,
                company_id=company.id,
                branch_id=branch_id,
                job_id=job_id,
                period_date=period_date,
                category=EconomicCategory.REVENUE,
                amount=1,
            )
        await AccountingPeriodService.transition(
            session,
            company.id,
            period.id,
            "reopened",
            TransitionAccountingPeriod(owner_id, "Approved late revenue correction."),
        )
        corrected = await _fact(
            session,
            company_id=company.id,
            branch_id=branch_id,
            job_id=job_id,
            period_date=period_date,
            category=EconomicCategory.REVENUE,
            amount=110_000,
            correction_kind="supersession",
            corrects_fact_id=facts[EconomicCategory.REVENUE].id,
        )
        assert corrected.corrects_fact_id == facts[EconomicCategory.REVENUE].id

        integrity_response = await EconomicsPhase4QueryService.financial_integrity(
            session, company.id, period.id
        )
        reconciliation_response = await EconomicsPhase4QueryService.reconciliation(
            session, company.id, period.id
        )
        audit_response = await EconomicsPhase4QueryService.audit_package(
            session, company.id, period.id
        )
        exports_response = await EconomicsPhase4QueryService.export_status(
            session, company.id, period.id
        )
        lineage_response = await EconomicsPhase4QueryService.projection_lineage(
            session, company.id, projection.id
        )
        assert not integrity_response.ready_to_close
        assert integrity_response.integrity_status == "stale"
        assert reconciliation_response.general_ledger_status == "passed"
        assert audit_response.package_digest == package.package_digest
        assert len(exports_response) == 2
        assert all(item.status == "acknowledged" for item in exports_response)
        assert lineage_response.integrity_status == "reconciled"

    async with economics_database() as session:
        history = int(
            await session.scalar(
                select(func.count())
                .select_from(AccountingPeriodHistoryRecord)
                .where(AccountingPeriodHistoryRecord.period_id == period.id)
            )
            or 0
        )
        publications = int(
            await session.scalar(
                select(func.count())
                .select_from(FinancialIntegrityPublicationRecord)
                .where(FinancialIntegrityPublicationRecord.company_id == company.id)
            )
            or 0
        )
        with pytest.raises(EconomicsPhase4NotFoundError):
            await EconomicsPhase4QueryService.audit_package(session, uuid4(), period.id)
    assert history == 4
    assert publications == 1


@pytest.mark.asyncio
async def test_scheduled_processing_retries_recovers_and_is_company_scoped(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    company = Company(
        name="Phase 4 Queue",
        code=f"P4Q{uuid4().hex[:8].upper()}",
        status="active",
        timezone="UTC",
    )
    async with economics_database() as session, session.begin():
        session.add(company)
        await session.flush()
        item = await EconomicsScheduledProcessingService.enqueue(
            session,
            company_id=company.id,
            kind="allocation",
            scope_type="company",
            scope_id=company.id,
            idempotency_key="phase4-retry-test",
            payload={},
            max_attempts=2,
        )
        duplicate = await EconomicsScheduledProcessingService.enqueue(
            session,
            company_id=company.id,
            kind="allocation",
            scope_type="company",
            scope_id=company.id,
            idempotency_key="phase4-retry-test",
        )
        assert duplicate.id == item.id
        attempted = await EconomicsScheduledProcessingService.process_next(session)
        assert attempted is not None
        assert attempted.status == "retry_scheduled"
        assert attempted.attempt_count == 1
        assert attempted.failure_evidence_digest is not None

        attempted.status = "processing"
        attempted.claimed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        recovered = await EconomicsScheduledProcessingService.recover_abandoned(session)
        assert recovered == 1
        assert attempted.status == "retry_scheduled"
        attempted.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        final = await EconomicsScheduledProcessingService.process_next(session)
        assert final is not None
        assert final.status == "failed"
        assert final.attempt_count == 2

        monitoring = await EconomicsScheduledProcessingService.enqueue(
            session,
            company_id=company.id,
            kind="monitoring",
            scope_type="company",
            scope_id=company.id,
            idempotency_key="phase4-monitoring-test",
        )
        completed = await EconomicsScheduledProcessingService.process_next(session)
        assert completed is not None
        assert completed.id == monitoring.id
        assert completed.status == "completed"

    async with economics_database() as session:
        records = tuple(
            (
                await session.scalars(
                    select(EconomicsProcessingWorkItem).where(
                        EconomicsProcessingWorkItem.company_id == company.id
                    )
                )
            ).all()
        )
    assert len(records) == 2
