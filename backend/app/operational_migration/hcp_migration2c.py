"""Sanctioned master orchestration for the SOURCE.4 HCP rehearsal."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    ApprovedCustomerImportBoundary,
    CustomerAdapterImportReport,
    CustomerAdapterImportService,
    ReviewedCustomerAdapterOutput,
    ReviewedCustomerAggregate,
)
from app.customer_migration.models import CustomerMigrationRun, CustomerSourceIdentity
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    FinancialMigrationService,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_migration2a import (
    UnlinkedEstimateEvidenceCommand,
    persist_unlinked_estimate_evidence,
)
from app.operational_migration.hcp_migration2b import (
    CustomerLineageCommand,
    EmployeeCrosswalkCommand,
    HoldCommand,
    MasterRunCommand,
    MasterRunOutcome,
    attest_master_run_outcome,
    canonical_sha256,
    persist_customer_lineage,
    persist_employee_crosswalk,
    persist_hold,
    prepare_master_run,
)
from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.hcp_rehearsal_authority import (
    SOURCE4_SYSTEM,
    require_sanctioned_context,
    require_sanctioned_target,
)
from app.operational_migration.models import (
    HcpCustomerSourceLineage,
    HcpEmployeeSourceCrosswalk,
    HcpMigrationHold,
    HcpMigrationMasterRun,
    OperationalMigrationRun,
    UnlinkedEstimateEvidence,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
    MigrationReport,
    OperationalMigrationService,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import UserCredential

REQUIRED_CHILD_DOMAINS = ("customer", "operational", "financial")
TERMINAL_CHILD_STATUSES = frozenset(
    {"completed", "completed_with_exceptions", "failed"}
)
COMPLETABLE_CHILD_STATUSES = frozenset({"completed", "completed_with_exceptions"})
ORCHESTRATOR_VERSION = "hcp-migration-2c-orchestrator/v1"


@dataclass(frozen=True)
class CompletionRequirements:
    customer_lineage: int
    employee_crosswalks: int
    holds_by_code: dict[str, int]
    hold_counts: dict[str, int]
    unlinked_estimates: int
    transformed_counts: dict[str, int]
    persisted_counts: dict[str, int]
    exception_counts: dict[str, int]
    rejection_counts: dict[str, int]
    unresolved_counts: dict[str, int]
    non_applicable_counts: dict[str, int]

    def validate_reconciliation(self, source_counts: dict[str, int]) -> None:
        keys = set(source_counts)
        outcomes = (
            self.persisted_counts,
            self.hold_counts,
            self.exception_counts,
            self.rejection_counts,
            self.unresolved_counts,
            self.non_applicable_counts,
        )
        if any(value < 0 for counts in outcomes for value in counts.values()):
            raise ValueError("negative reconciliation count")
        for entity in keys:
            accounted = sum(
                counts.get(entity, 0)
                for counts in (
                    self.persisted_counts,
                    self.exception_counts,
                    self.rejection_counts,
                    self.unresolved_counts,
                    self.non_applicable_counts,
                )
            )
            accounted += self.hold_counts.get(entity, 0)
            if accounted != source_counts[entity]:
                raise ValueError(f"aggregate reconciliation mismatch for {entity}")


class HcpMigration2Orchestrator:
    """Own the master-first lifecycle while delegating domain business logic."""

    def __init__(
        self,
        *,
        customer_service: CustomerAdapterImportService | None = None,
        operational_service: OperationalMigrationService | None = None,
        financial_service: FinancialMigrationService | None = None,
    ) -> None:
        self._customers = customer_service or CustomerAdapterImportService()
        self._operations = operational_service or OperationalMigrationService()
        self._financials = financial_service or FinancialMigrationService()

    @staticmethod
    async def _authorize(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
    ) -> str:
        require_sanctioned_context(context)
        target_digest = require_sanctioned_target(target)
        database, address, port = (
            await session.execute(
                select(
                    func.current_database(),
                    func.inet_server_addr(),
                    func.inet_server_port(),
                )
            )
        ).one()
        parsed = urlparse(target.database_url)
        if (
            database != target.expected_database
            or str(address) not in {"127.0.0.1", "::1"}
            or parsed.port != port
        ):
            raise ValueError("database session does not match sanctioned target")
        credential_count = await session.scalar(
            select(func.count())
            .select_from(UserCredential)
            .where(UserCredential.user_id == context.user.id)
        )
        if credential_count:
            raise ValueError("rehearsal actor must remain credential-less")
        return target_digest

    async def start_or_resume(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        target: NonProductionTarget,
        command: MasterRunCommand,
    ) -> tuple[HcpMigrationMasterRun, bool]:
        target_digest = await self._authorize(session, context=context, target=target)
        branch = context.active_branch
        assert branch is not None
        if command.implementation_version != ORCHESTRATOR_VERSION:
            raise ValueError("unexpected orchestration implementation version")
        expected_input_digest = canonical_sha256(
            command.input_payload(
                company_id=context.company.id,
                branch_id=branch.id,
                actor_id=context.user.id,
            )
        )
        existing_package_run = await session.scalar(
            select(HcpMigrationMasterRun).where(
                HcpMigrationMasterRun.company_id == context.company.id,
                HcpMigrationMasterRun.branch_id == branch.id,
                HcpMigrationMasterRun.package_digest == command.package_digest,
            )
        )
        if (
            existing_package_run is not None
            and existing_package_run.input_digest != expected_input_digest
        ):
            raise ValueError("immutable master input changed during replay or resume")
        run, created = await prepare_master_run(
            session, context=context, command=command
        )
        if run.status in {"completed", "failed"}:
            return run, False
        if run.status not in {"prepared", "interrupted", "running"}:
            raise ValueError("master run cannot be resumed from its current state")
        run.status = "running"
        run.resume_state = {
            "state": "running",
            "target_digest": target_digest,
            "last_authoritative_checkpoint": run.resume_state.get("cursor"),
        }
        prior_attempt = run.replay_state.get("attempt", 0)
        if not isinstance(prior_attempt, int):
            raise TypeError("master replay attempt state is invalid")
        run.replay_state = {
            "attempt": prior_attempt + 1,
            "state": "running",
        }
        await session.flush()
        return run, created

    @staticmethod
    async def _active_master(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
    ) -> HcpMigrationMasterRun:
        require_sanctioned_context(context)
        database, address = (
            await session.execute(
                select(func.current_database(), func.inet_server_addr())
            )
        ).one()
        if database != "acp_hcp_rehearsal_import" or str(address) not in {
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                "active session is outside the sanctioned rehearsal target"
            )
        run = await session.get(HcpMigrationMasterRun, master_run_id)
        if (
            run is None
            or run.company_id != context.company.id
            or context.active_branch is None
            or run.branch_id != context.active_branch.id
            or run.actor_user_id != context.user.id
            or run.status != "running"
        ):
            raise ValueError("active scoped master run is required")
        return run

    async def run_customers(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        reviewed: ReviewedCustomerAdapterOutput,
        boundary: ApprovedCustomerImportBoundary,
    ) -> CustomerAdapterImportReport:
        if reviewed.source_system != SOURCE4_SYSTEM:
            raise ValueError("orchestrator requires SOURCE.4 Customer identity")
        async with factory() as session:
            await self._active_master(
                session, context=context, master_run_id=master_run_id
            )
            existing = await session.scalar(
                select(CustomerMigrationRun).where(
                    CustomerMigrationRun.master_run_id == master_run_id
                )
            )
            if existing is not None:
                if existing.status != "completed":
                    raise ValueError(
                        "Customer child requires explicit failed-run repair"
                    )
                return CustomerAdapterImportReport(
                    run_id=str(existing.id),
                    attempted=existing.source_count,
                    accepted=existing.accepted_count,
                    duplicate=existing.duplicate_count,
                    rejected=existing.rejected_count,
                )

        async def lineage(
            session: AsyncSession,
            identity: CustomerSourceIdentity,
            aggregate: ReviewedCustomerAggregate,
        ) -> None:
            await persist_customer_lineage(
                session,
                context=context,
                master_run_id=master_run_id,
                command=CustomerLineageCommand(
                    native_customer_id=aggregate.source_identity,
                    source_digest=aggregate.source_row_sha256,
                    transformation_contract=reviewed.schema_version,
                    transformation_digest=reviewed.transformation_sha256,
                    source_timestamps={},
                    source_context={"row_number": aggregate.row_number},
                    customer_source_identity_id=identity.id,
                ),
            )

        return await self._customers.run(
            factory,
            context=context,
            reviewed=reviewed,
            boundary=boundary,
            master_run_id=master_run_id,
            lineage_callback=lineage,
        )

    async def run_operational(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        jobs: tuple[JobMigrationRecord, ...],
        appointments: tuple[AppointmentMigrationRecord, ...],
    ) -> MigrationReport:
        async with factory() as session:
            await self._active_master(
                session, context=context, master_run_id=master_run_id
            )
            existing = await session.scalar(
                select(OperationalMigrationRun).where(
                    OperationalMigrationRun.master_run_id == master_run_id,
                    OperationalMigrationRun.master_domain == "operational",
                )
            )
            if existing is not None:
                if existing.status not in COMPLETABLE_CHILD_STATUSES:
                    raise ValueError(
                        "Operational child requires explicit failed-run repair"
                    )
                return MigrationReport(
                    existing.id,
                    existing.mode,
                    existing.source_count,
                    existing.accepted_count,
                    existing.rejected_count,
                    existing.duplicate_count,
                    existing.unresolved_count,
                )
        return await self._operations.run(
            factory,
            context=context,
            source_system=SOURCE4_SYSTEM,
            jobs=jobs,
            appointments=appointments,
            dry_run=False,
            master_run_id=master_run_id,
        )

    async def run_financial(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        estimates: tuple[EstimateMigrationRecord, ...],
        invoices: tuple[InvoiceMigrationRecord, ...],
        payments: tuple[PaymentMigrationRecord, ...],
    ) -> MigrationReport:
        async with factory() as session:
            await self._active_master(
                session, context=context, master_run_id=master_run_id
            )
            existing = await session.scalar(
                select(OperationalMigrationRun).where(
                    OperationalMigrationRun.master_run_id == master_run_id,
                    OperationalMigrationRun.master_domain == "financial",
                )
            )
            if existing is not None:
                if existing.status not in COMPLETABLE_CHILD_STATUSES:
                    raise ValueError(
                        "Financial child requires explicit failed-run repair"
                    )
                return MigrationReport(
                    existing.id,
                    existing.mode,
                    existing.source_count,
                    existing.accepted_count,
                    existing.rejected_count,
                    existing.duplicate_count,
                    existing.unresolved_count,
                )
        return await self._financials.run(
            factory,
            context=context,
            source_system=SOURCE4_SYSTEM,
            estimates=estimates,
            invoices=invoices,
            payments=payments,
            dry_run=False,
            master_run_id=master_run_id,
        )

    async def persist_employee(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        command: EmployeeCrosswalkCommand,
    ) -> bool:
        await self._active_master(session, context=context, master_run_id=master_run_id)
        _, created = await persist_employee_crosswalk(
            session,
            context=context,
            master_run_id=master_run_id,
            command=command,
        )
        return created

    async def persist_held_subject(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        command: HoldCommand,
    ) -> bool:
        await self._active_master(session, context=context, master_run_id=master_run_id)
        _, created = await persist_hold(
            session,
            context=context,
            master_run_id=master_run_id,
            command=command,
        )
        return created

    async def persist_unlinked_estimate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        command: UnlinkedEstimateEvidenceCommand,
    ) -> UnlinkedEstimateEvidence:
        await self._active_master(session, context=context, master_run_id=master_run_id)
        if command.synthetic_qualification:
            raise ValueError(
                "real master cannot persist synthetic qualification evidence"
            )
        return await persist_unlinked_estimate_evidence(
            session,
            context=context,
            command=command,
            master_run_id=master_run_id,
        )

    async def interrupt(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        checkpoint: str,
        reason_code: str,
    ) -> HcpMigrationMasterRun:
        run = await self._active_master(
            session, context=context, master_run_id=master_run_id
        )
        if not checkpoint or not reason_code:
            raise ValueError("checkpoint and interruption reason are required")
        run.status = "interrupted"
        run.resume_state = {
            "state": "interrupted",
            "cursor": checkpoint,
            "reason_code": reason_code,
        }
        run.rollback_state = {
            "business_rows": "retained_for_idempotent_resume",
            "audit_evidence": "retained_immutable",
            "source_evidence": "retained_immutable",
            "financial_truth": "not_promoted",
        }
        await session.flush()
        return run

    async def complete(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        expected_input_digest: str,
        requirements: CompletionRequirements,
    ) -> HcpMigrationMasterRun:
        run = await self._active_master(
            session, context=context, master_run_id=master_run_id
        )
        customer_run = await session.scalar(
            select(CustomerMigrationRun).where(
                CustomerMigrationRun.master_run_id == master_run_id
            )
        )
        operational_runs = tuple(
            (
                await session.scalars(
                    select(OperationalMigrationRun).where(
                        OperationalMigrationRun.master_run_id == master_run_id
                    )
                )
            ).all()
        )
        by_domain = {item.master_domain: item for item in operational_runs}
        if customer_run is None or set(by_domain) != {"operational", "financial"}:
            raise ValueError("required child migration run is missing")
        child_runs: dict[str, CustomerMigrationRun | OperationalMigrationRun] = {
            "customer": customer_run,
            "operational": by_domain["operational"],
            "financial": by_domain["financial"],
        }
        if any(
            item.status not in TERMINAL_CHILD_STATUSES for item in child_runs.values()
        ):
            raise ValueError("required child migration run is non-terminal")
        if any(
            item.status not in COMPLETABLE_CHILD_STATUSES
            for item in child_runs.values()
        ):
            raise ValueError("failed child migration run prevents master completion")

        lineage_count = await session.scalar(
            select(func.count())
            .select_from(HcpCustomerSourceLineage)
            .where(HcpCustomerSourceLineage.master_run_id == master_run_id)
        )
        employee_count = await session.scalar(
            select(func.count())
            .select_from(HcpEmployeeSourceCrosswalk)
            .where(HcpEmployeeSourceCrosswalk.master_run_id == master_run_id)
        )
        unlinked_count = await session.scalar(
            select(func.count())
            .select_from(UnlinkedEstimateEvidence)
            .where(
                UnlinkedEstimateEvidence.master_run_id == master_run_id,
                UnlinkedEstimateEvidence.synthetic_qualification.is_(False),
            )
        )
        hold_rows = tuple(
            (
                await session.scalars(
                    select(HcpMigrationHold).where(
                        HcpMigrationHold.master_run_id == master_run_id,
                        HcpMigrationHold.state == "HELD",
                    )
                )
            ).all()
        )
        holds_by_code: dict[str, int] = {}
        hold_counts: dict[str, int] = {}
        for hold in hold_rows:
            holds_by_code[hold.hold_code] = holds_by_code.get(hold.hold_code, 0) + 1
            hold_counts[hold.entity_kind] = hold_counts.get(hold.entity_kind, 0) + 1
        if (
            lineage_count != requirements.customer_lineage
            or lineage_count != customer_run.accepted_count
        ):
            raise ValueError("Customer success is missing immutable SOURCE.4 lineage")
        if employee_count != requirements.employee_crosswalks:
            raise ValueError("Employee crosswalk reconciliation is incomplete")
        if holds_by_code != requirements.holds_by_code:
            raise ValueError("HOLD reconciliation is incomplete")
        if hold_counts != requirements.hold_counts:
            raise ValueError("HOLD entity accounting is incomplete")
        if unlinked_count != requirements.unlinked_estimates:
            raise ValueError("unlinked Estimate reconciliation is incomplete")
        requirements.validate_reconciliation(run.source_counts)

        child_run_ids = {
            domain: str(child.id) for domain, child in sorted(child_runs.items())
        }
        outcome = MasterRunOutcome(
            transformed_counts=requirements.transformed_counts,
            persisted_counts=requirements.persisted_counts,
            hold_counts=requirements.hold_counts,
            exception_counts=requirements.exception_counts,
            rejection_counts=requirements.rejection_counts,
            unresolved_counts=requirements.unresolved_counts,
            non_applicable_counts=requirements.non_applicable_counts,
            child_run_ids=child_run_ids,
            replay_state={"state": "completed", "deterministic": True},
            resume_state={"state": "completed", "cursor": "reconciled"},
            status="completed",
        )
        run.rollback_state = {
            "business_rows": "retained_until_separate_pre_cutover_authorization",
            "audit_evidence": "retained_immutable",
            "source_evidence": "retained_immutable",
            "financial_truth": "held_unless_explicitly_accepted",
        }
        completed = await attest_master_run_outcome(
            session,
            context=context,
            run_id=master_run_id,
            expected_input_digest=expected_input_digest,
            outcome=outcome,
        )
        await session.flush()
        return completed
