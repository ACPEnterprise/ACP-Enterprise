"""Append-only repositories for deterministic cutover planning and rehearsal."""

import json
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.cutover_plan import CUTOVER_PLAN_VERSION, CutoverPlan
from app.customer_migration.cutover_rehearsal import (
    CUTOVER_REHEARSAL_VERSION,
    CutoverRehearsal,
)
from app.customer_migration.models import (
    CustomerMigrationCutoverPlanEvidence,
    CustomerMigrationCutoverRehearsalEvidence,
    CustomerMigrationCutoverRehearsalStepEvidence,
)


def _jsonable(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


@dataclass(frozen=True)
class CutoverPlanWrite:
    company_id: UUID
    branch_id: UUID
    planned_by_user_id: UUID
    plan: CutoverPlan


class CutoverPlanEvidenceRepository:
    async def record(
        self, session: AsyncSession, *, evidence: CutoverPlanWrite
    ) -> tuple[CustomerMigrationCutoverPlanEvidence, bool]:
        plan = evidence.plan
        existing = await session.scalar(
            select(CustomerMigrationCutoverPlanEvidence).where(
                CustomerMigrationCutoverPlanEvidence.company_id == evidence.company_id,
                CustomerMigrationCutoverPlanEvidence.branch_id == evidence.branch_id,
                CustomerMigrationCutoverPlanEvidence.evidence_digest
                == plan.plan_digest,
            )
        )
        if existing is not None:
            return existing, False
        if (
            plan.company_id != evidence.company_id
            or plan.branch_id != evidence.branch_id
        ):
            raise ValueError("cutover plan scope does not match repository scope")
        record = CustomerMigrationCutoverPlanEvidence(
            id=plan.plan_id,
            company_id=evidence.company_id,
            branch_id=evidence.branch_id,
            readiness_evidence_id=plan.readiness_evidence_id,
            planned_by_user_id=evidence.planned_by_user_id,
            plan_key=plan.plan_digest,
            contract_version=CUTOVER_PLAN_VERSION,
            plan_version=plan.version.version,
            status="ready_for_owner_approval"
            if plan.assessment.eligible
            else "blocked",
            plan_metadata=_jsonable(
                {
                    "source_provider": plan.source_provider,
                    "source_environment": plan.source_environment,
                    "transformation_contract_versions": plan.transformation_contract_versions,
                    "migration_schema_lineage": plan.migration_schema_lineage,
                    "readiness_evidence_digest": plan.readiness_evidence_digest,
                    "owner_disposition_summary": plan.owner_disposition_summary,
                    "reconciliation_summary": plan.reconciliation_summary,
                    "created_by_user_id": plan.created_by_user_id,
                    "created_at": plan.created_at,
                    "version": asdict(plan.version),
                }
            ),
            ordered_steps=_jsonable([asdict(item) for item in plan.ordered_steps]),
            dependency_graph=_jsonable([asdict(item) for item in plan.dependencies]),
            preconditions=_jsonable([asdict(item) for item in plan.preconditions]),
            rollback_prerequisites=_jsonable(
                [asdict(item) for item in plan.rollback_requirements]
            ),
            owner_checkpoints=_jsonable([asdict(item) for item in plan.checkpoints]),
            blocking_conditions=[
                item.code for item in plan.assessment.blocking_conditions
            ],
            required_approvals=_jsonable(list(plan.assessment.required_approvals)),
            recovery_instructions=_jsonable(
                [asdict(item) for item in plan.recovery_instructions]
            ),
            evidence_digest=plan.plan_digest,
            created_at=plan.created_at,
        )
        values = {
            column.name: getattr(record, column.name)
            for column in CustomerMigrationCutoverPlanEvidence.__table__.columns
        }
        inserted_id = await session.scalar(
            insert(CustomerMigrationCutoverPlanEvidence)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["company_id", "branch_id", "evidence_digest"]
            )
            .returning(CustomerMigrationCutoverPlanEvidence.id)
        )
        stored = await session.scalar(
            select(CustomerMigrationCutoverPlanEvidence).where(
                CustomerMigrationCutoverPlanEvidence.company_id == evidence.company_id,
                CustomerMigrationCutoverPlanEvidence.branch_id == evidence.branch_id,
                CustomerMigrationCutoverPlanEvidence.evidence_digest
                == plan.plan_digest,
            )
        )
        if stored is None:
            raise RuntimeError("cutover plan evidence insert was not observable")
        return stored, inserted_id is not None

    async def record_rehearsal(
        self, session: AsyncSession, *, rehearsal: CutoverRehearsal
    ) -> tuple[CustomerMigrationCutoverRehearsalEvidence, bool]:
        existing = await session.scalar(
            select(CustomerMigrationCutoverRehearsalEvidence).where(
                CustomerMigrationCutoverRehearsalEvidence.company_id
                == rehearsal.company_id,
                CustomerMigrationCutoverRehearsalEvidence.branch_id
                == rehearsal.branch_id,
                CustomerMigrationCutoverRehearsalEvidence.plan_id == rehearsal.plan_id,
                CustomerMigrationCutoverRehearsalEvidence.evidence_digest
                == rehearsal.evidence_digest,
            )
        )
        if existing is not None:
            return existing, False
        record = CustomerMigrationCutoverRehearsalEvidence(
            id=rehearsal.rehearsal_id,
            company_id=rehearsal.company_id,
            branch_id=rehearsal.branch_id,
            plan_id=rehearsal.plan_id,
            created_by_user_id=rehearsal.created_by_user_id,
            contract_version=CUTOVER_REHEARSAL_VERSION,
            version=rehearsal.version,
            status=rehearsal.status,
            evidence_digest=rehearsal.evidence_digest,
            created_at=rehearsal.created_at,
        )
        values = {
            column.name: getattr(record, column.name)
            for column in CustomerMigrationCutoverRehearsalEvidence.__table__.columns
        }
        inserted_id = await session.scalar(
            insert(CustomerMigrationCutoverRehearsalEvidence)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["company_id", "branch_id", "plan_id", "evidence_digest"]
            )
            .returning(CustomerMigrationCutoverRehearsalEvidence.id)
        )
        stored = await session.scalar(
            select(CustomerMigrationCutoverRehearsalEvidence).where(
                CustomerMigrationCutoverRehearsalEvidence.company_id
                == rehearsal.company_id,
                CustomerMigrationCutoverRehearsalEvidence.branch_id
                == rehearsal.branch_id,
                CustomerMigrationCutoverRehearsalEvidence.plan_id == rehearsal.plan_id,
                CustomerMigrationCutoverRehearsalEvidence.evidence_digest
                == rehearsal.evidence_digest,
            )
        )
        if stored is None:
            raise RuntimeError("cutover rehearsal evidence insert was not observable")
        if inserted_id is None:
            return stored, False
        for result in rehearsal.step_results:
            step = CustomerMigrationCutoverRehearsalStepEvidence(
                company_id=rehearsal.company_id,
                branch_id=rehearsal.branch_id,
                rehearsal_id=stored.id,
                step_id=result.step_id,
                step_code=result.step_code,
                ordinal=result.ordinal,
                outcome=result.outcome,
                failure_code=result.failure_code,
                recovery_instruction_code=result.recovery_instruction_code,
                evidence_digest=result.evidence_digest,
            )
            session.add(step)
        await session.flush()
        return stored, True


class CutoverPlanningEvidenceService:
    """Own transactions for append-only plan and rehearsal writes."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        repository: CutoverPlanEvidenceRepository | None = None,
    ) -> None:
        self._factory = factory
        self._repository = repository or CutoverPlanEvidenceRepository()

    async def record_plan(
        self, evidence: CutoverPlanWrite
    ) -> tuple[CustomerMigrationCutoverPlanEvidence, bool]:
        async with self._factory() as session, session.begin():
            return await self._repository.record(session, evidence=evidence)

    async def record_rehearsal(
        self, rehearsal: CutoverRehearsal
    ) -> tuple[CustomerMigrationCutoverRehearsalEvidence, bool]:
        async with self._factory() as session, session.begin():
            return await self._repository.record_rehearsal(session, rehearsal=rehearsal)


cutover_plan_evidence_repository = CutoverPlanEvidenceRepository()
