from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.events.models import BusinessEvent
from app.operational_migration.cutover import (
    ArtifactMigrationRecord,
    CutoverMigrationService,
    HistoryMigrationRecord,
)
from app.operational_migration.cutover_models import (
    MigrationArtifact,
    MigrationArtifactAttempt,
    MigrationAuditSummary,
    MigrationHistoryEntry,
    MigrationRecordOutcome,
)
from app.operational_migration.cutover_repository import (
    CutoverMigrationRepository,
)
from app.operational_migration.models import OperationalMigrationRun
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from tests.operational_migration.test_operational_migration import (
    NOW,
    seed_context,
    seed_migrated_customer,
    seed_migrated_job,
)


@pytest_asyncio.fixture
async def cutover_database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_parents(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
    tmp_path,
) -> None:
    await seed_migrated_customer(factory, context=context, tmp_path=tmp_path)
    await seed_migrated_job(factory, context=context)


async def seed_employee(
    factory: async_sessionmaker[AsyncSession],
    *,
    context: AuthorizationContext,
) -> Employee:
    async with factory() as session, session.begin():
        employee = Employee(
            company_id=context.company.id,
            membership_id=context.membership.id,
            home_branch_id=context.active_branch.id,
            employee_number=f"SYN-{uuid4().hex[:8]}",
            first_name="Synthetic",
            last_name="Technician",
            display_name="Synthetic Technician",
            employee_type="employee",
            status="active",
        )
        session.add(employee)
        await session.flush()
    return employee


def history_records() -> list[HistoryMigrationRecord]:
    return [
        HistoryMigrationRecord(
            source_id="history-note-1",
            parent_type="customer",
            source_parent_id="customer-1",
            entry_type="note",
            occurred_at=NOW,
            summary_text="Synthetic historical service preference.",
            activity_category="customer_context",
            tags=("vip", "source-only-tag"),
            attributes={
                "source_status": "archived",
                "unsupported_key": "visible-by-key-only",
            },
        ),
        HistoryMigrationRecord(
            source_id="history-activity-1",
            parent_type="job",
            source_parent_id="financial-job-1",
            entry_type="activity",
            occurred_at=NOW,
            summary_text="Synthetic dispatch activity.",
            activity_category="dispatch",
            employee_source_reference="source-employee-unresolved",
        ),
        HistoryMigrationRecord(
            source_id="history-missing-parent",
            parent_type="job",
            source_parent_id="missing-job",
            entry_type="note",
            occurred_at=NOW,
            summary_text="Synthetic unresolved parent record.",
            activity_category="history",
        ),
        HistoryMigrationRecord(
            source_id="history-wrong-employee",
            parent_type="customer",
            source_parent_id="customer-1",
            entry_type="activity",
            occurred_at=NOW,
            summary_text="Synthetic invalid employee scope.",
            activity_category="sales",
            employee_source_reference="wrong-company-employee",
            target_employee_id=uuid4(),
        ),
    ]


def artifact_records() -> list[ArtifactMigrationRecord]:
    return [
        ArtifactMigrationRecord(
            source_id="artifact-transferred",
            parent_type="customer",
            source_parent_id="customer-1",
            artifact_category="document",
            original_filename="synthetic-summary.pdf",
            media_type="application/pdf",
            byte_size=128,
            source_checksum="sha256:synthetic-source-a",
            acp_checksum="sha256:synthetic-acp-a",
            transfer_outcome="transferred",
        ),
        ArtifactMigrationRecord(
            source_id="artifact-retryable",
            parent_type="job",
            source_parent_id="financial-job-1",
            artifact_category="photo",
            original_filename="synthetic-photo.jpg",
            media_type="image/jpeg",
            byte_size=64,
            source_checksum="sha256:synthetic-source-b",
            transfer_outcome="retryable_failure",
            failure_classification="synthetic_transient_failure",
        ),
        ArtifactMigrationRecord(
            source_id="artifact-nonretryable",
            parent_type="job",
            source_parent_id="financial-job-1",
            artifact_category="attachment",
            original_filename="synthetic-unavailable.txt",
            media_type="text/plain",
            byte_size=12,
            source_checksum="sha256:synthetic-source-c",
            transfer_outcome="nonretryable_failure",
            failure_classification="synthetic_source_unavailable",
        ),
        ArtifactMigrationRecord(
            source_id="artifact-duplicate-checksum",
            parent_type="customer",
            source_parent_id="customer-1",
            artifact_category="document",
            original_filename="synthetic-duplicate.pdf",
            media_type="application/pdf",
            byte_size=128,
            source_checksum="sha256:synthetic-source-a",
            transfer_outcome="pending",
        ),
    ]


@pytest.mark.asyncio
async def test_cutover_history_artifacts_retry_and_not_ready(
    cutover_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path,
) -> None:
    _, factory = cutover_database
    context = await seed_context(factory)
    await seed_parents(factory, context=context, tmp_path=tmp_path)
    employee = await seed_employee(factory, context=context)
    service = CutoverMigrationService()
    history = history_records()
    history.append(
        HistoryMigrationRecord(
            source_id="history-resolved-employee",
            parent_type="job",
            source_parent_id="financial-job-1",
            entry_type="activity",
            occurred_at=NOW,
            summary_text="Synthetic resolved technician activity.",
            activity_category="service",
            employee_source_reference="source-employee-resolved",
            target_employee_id=employee.id,
        )
    )

    dry_run = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        history=history,
        artifacts=artifact_records(),
        dry_run=True,
    )
    assert (
        dry_run.source,
        dry_run.accepted,
        dry_run.rejected,
        dry_run.duplicate,
        dry_run.unresolved,
    ) == (9, 6, 1, 1, 1)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationHistoryEntry)
                .where(MigrationHistoryEntry.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationArtifact)
                .where(MigrationArtifact.company_id == context.company.id)
            )
            == 0
        )

    imported = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        history=history,
        artifacts=artifact_records(),
        dry_run=False,
    )
    assert (
        imported.source,
        imported.accepted,
        imported.rejected,
        imported.duplicate,
        imported.unresolved,
    ) == (9, 6, 1, 1, 1)
    async with factory() as session:
        entries = list(
            (
                await session.scalars(
                    select(MigrationHistoryEntry).where(
                        MigrationHistoryEntry.company_id == context.company.id
                    )
                )
            ).all()
        )
        assert len(entries) == 3
        note = next(item for item in entries if item.entry_type == "note")
        activity = next(item for item in entries if item.entry_type == "activity")
        assert note.supported_tags == ["vip"]
        assert note.normalized_attributes == {"source_status": "archived"}
        assert note.unsupported_attribute_keys == [
            "tag:source-only-tag",
            "unsupported_key",
        ]
        assert activity.attribution_status == "unresolved"
        assert activity.employee_source_ref_sha256 != "source-employee-unresolved"
        resolved = next(item for item in entries if item.employee_id == employee.id)
        assert resolved.attribution_status == "resolved"
        outcomes = list(
            (
                await session.scalars(
                    select(MigrationRecordOutcome).where(
                        MigrationRecordOutcome.run_id == imported.run_id
                    )
                )
            ).all()
        )
        assert len(outcomes) == 9
        assert all(len(item.source_id_sha256) == 64 for item in outcomes)

    rerun = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        history=history,
        artifacts=artifact_records(),
        dry_run=False,
    )
    assert (
        rerun.source,
        rerun.accepted,
        rerun.rejected,
        rerun.duplicate,
        rerun.unresolved,
    ) == (9, 0, 1, 7, 1)

    retried = await service.retry_artifact(
        factory,
        context=context,
        source_system="housecall_pro",
        source_id="artifact-retryable",
        acp_checksum="sha256:synthetic-acp-retry",
    )
    assert retried.transfer_state == "transferred"
    with pytest.raises(ValueError, match="not retryable"):
        await service.retry_artifact(
            factory,
            context=context,
            source_system="housecall_pro",
            source_id="artifact-nonretryable",
            acp_checksum="sha256:unused",
        )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationArtifactAttempt)
                .where(MigrationArtifactAttempt.artifact_id == retried.id)
            )
            == 2
        )

    readiness = await service.assess_readiness(
        factory,
        context=context,
        required_phases=("phase1", "phase2", "phase3", "phase4", "phase5"),
    )
    assert readiness.ready is False
    assert {
        "unresolved_parents",
        "unresolved_employee_references",
        "required_artifacts_incomplete",
        "required_phases_incomplete",
    }.issubset(readiness.blocker_codes)
    summary = await service.complete(
        factory,
        context=context,
        readiness=readiness,
        source_descriptor="synthetic source descriptor",
    )
    assert summary.completion_status == "completed_with_exceptions"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.event_type == "migration.completed_with_exceptions",
                )
            )
            == 1
        )
    assert "Synthetic historical service preference." not in str(summary.entity_counts)


@pytest.mark.asyncio
async def test_cutover_interrupt_resume_ready_and_completion(
    cutover_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path,
) -> None:
    _, factory = cutover_database
    context = await seed_context(factory)
    await seed_parents(factory, context=context, tmp_path=tmp_path)
    service = CutoverMigrationService()
    history = [
        HistoryMigrationRecord(
            source_id="resume-note-1",
            parent_type="customer",
            source_parent_id="customer-1",
            entry_type="note",
            occurred_at=NOW,
            summary_text="Synthetic resumable note one.",
            activity_category="history",
        ),
        HistoryMigrationRecord(
            source_id="resume-note-2",
            parent_type="job",
            source_parent_id="financial-job-1",
            entry_type="activity",
            occurred_at=NOW,
            summary_text="Synthetic resumable activity two.",
            activity_category="history",
        ),
    ]
    artifacts = [
        ArtifactMigrationRecord(
            source_id="resume-artifact-1",
            parent_type="job",
            source_parent_id="financial-job-1",
            artifact_category="document",
            original_filename="resume-synthetic.pdf",
            media_type="application/pdf",
            byte_size=32,
            source_checksum="sha256:resume-synthetic",
            acp_checksum="sha256:resume-acp",
            transfer_outcome="transferred",
        )
    ]
    interrupted = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        history=history,
        artifacts=artifacts,
        dry_run=False,
        interrupt_after=1,
    )
    assert interrupted.source == interrupted.accepted == 1
    async with factory() as session:
        run = await session.get(OperationalMigrationRun, interrupted.run_id)
        assert run is not None and run.status == "interrupted"
    interrupted_readiness = await service.assess_readiness(
        factory,
        context=context,
        required_phases=("phase1", "phase2", "phase3", "phase4", "phase5"),
    )
    incomplete_summary = await service.complete(
        factory,
        context=context,
        readiness=interrupted_readiness,
        source_descriptor="synthetic interrupted descriptor",
    )
    assert incomplete_summary.completion_status == "incomplete"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.event_type.in_(
                        {
                            "migration.completed",
                            "migration.completed_with_exceptions",
                        }
                    ),
                )
            )
            == 0
        )

    resumed = await service.run(
        factory,
        context=context,
        source_system="housecall_pro",
        history=history,
        artifacts=artifacts,
        dry_run=False,
        resume_run_id=interrupted.run_id,
    )
    assert resumed.source == resumed.accepted == 3
    async with factory() as session:
        run = await session.get(OperationalMigrationRun, resumed.run_id)
        assert run is not None and run.status == "completed"

    for phase in ("phase1", "phase2", "phase3", "phase4", "phase5"):
        await service.record_phase_completion(
            factory,
            context=context,
            phase_code=phase,
            supporting_run_id=resumed.run_id,
            dry_run_completed=True,
            import_completed=True,
            idempotent_rerun_validated=True,
        )
    readiness = await service.assess_readiness(
        factory,
        context=context,
        required_phases=("phase1", "phase2", "phase3", "phase4", "phase5"),
    )
    assert readiness.ready is True
    assert readiness.blocker_codes == ()
    assert readiness.facts["source_records"] == 3
    assert readiness.facts["accepted"] == 3
    summary = await service.complete(
        factory,
        context=context,
        readiness=readiness,
        source_descriptor="synthetic resume descriptor",
    )
    assert summary.completion_status == "completed"
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationAuditSummary)
                .where(MigrationAuditSummary.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(
                    BusinessEvent.company_id == context.company.id,
                    BusinessEvent.event_type == "migration.completed",
                )
            )
            == 1
        )


class FailingCutoverRepository(CutoverMigrationRepository):
    @staticmethod
    def add_history(session: AsyncSession, entry: MigrationHistoryEntry) -> None:
        CutoverMigrationRepository.add_history(session, entry)
        raise RuntimeError("synthetic cutover transaction failure")


@pytest.mark.asyncio
async def test_cutover_record_rollback_has_no_partial_identity(
    cutover_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],
    tmp_path,
) -> None:
    _, factory = cutover_database
    context = await seed_context(factory)
    await seed_parents(factory, context=context, tmp_path=tmp_path)
    service = CutoverMigrationService(repository=FailingCutoverRepository())
    record = HistoryMigrationRecord(
        source_id="rollback-note",
        parent_type="customer",
        source_parent_id="customer-1",
        entry_type="note",
        occurred_at=NOW,
        summary_text="Synthetic rollback note.",
        activity_category="history",
    )

    with pytest.raises(RuntimeError, match="synthetic cutover transaction failure"):
        await service.run(
            factory,
            context=context,
            source_system="housecall_pro",
            history=[record],
            artifacts=[],
            dry_run=False,
        )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationHistoryEntry)
                .where(MigrationHistoryEntry.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MigrationRecordOutcome)
                .join(
                    OperationalMigrationRun,
                    OperationalMigrationRun.id == MigrationRecordOutcome.run_id,
                )
                .where(OperationalMigrationRun.company_id == context.company.id)
            )
            == 0
        )
