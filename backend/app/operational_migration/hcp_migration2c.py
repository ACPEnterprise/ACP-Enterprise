"""Sanctioned master orchestration for the SOURCE.4 HCP rehearsal."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from urllib.parse import urlparse
from uuid import UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    ApprovedCustomerImportBoundary,
    CustomerAdapterImportReport,
    CustomerAdapterImportService,
    ReviewedCustomerAdapterOutput,
    ReviewedCustomerAggregate,
)
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationChildException,
    CustomerMigrationRun,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import ServiceLocation
from app.operational_migration.cutover import (
    CutoverMigrationService,
    HistoryMigrationRecord,
)
from app.operational_migration.financial import (
    EstimateMigrationRecord,
    FinancialMigrationService,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_hybrid_customer import (
    HybridCustomerAdmission,
    JobParentClosure,
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
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import UserCredential

REQUIRED_CHILD_DOMAINS = ("customer", "operational", "financial", "history")
REQUIRED_SOURCE4_ENTITIES = frozenset(
    {
        "customer",
        "contact",
        "service_location",
        "employee",
        "job",
        "appointment",
        "estimate",
        "invoice",
        "payment",
        "note",
    }
)
TERMINAL_CHILD_STATUSES = frozenset(
    {"completed", "completed_with_exceptions", "failed"}
)
COMPLETABLE_CHILD_STATUSES = frozenset({"completed", "completed_with_exceptions"})
ORCHESTRATOR_VERSION = "hcp-migration-2f-orchestrator/v1"
EMPLOYEE_NAMESPACE = UUID("82f43837-ceec-5d02-bb92-cf65b9ac6af8")
STAGING_NAMESPACE = UUID("b2ad788f-ae3a-5e22-8b12-4937bf65e44f")


@dataclass(frozen=True)
class HybridCustomerStagingReport:
    artifact_id: UUID
    staging_digest: str
    customers: int
    contacts: int
    locations: int
    child_exceptions: int
    reused: bool


@dataclass(frozen=True)
class EmployeeCandidateCommand:
    native_employee_id: str
    disposition: str
    source_digest: str
    owner_receipt_digest: str
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    job_title: str | None = None

    def validate(self) -> None:
        EmployeeCrosswalkCommand(
            native_employee_id=self.native_employee_id,
            disposition=self.disposition,
            source_digest=self.source_digest,
            owner_receipt_digest=self.owner_receipt_digest,
        ).validate()
        if self.disposition == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE":
            if not all(
                value is not None and value.strip()
                for value in (self.first_name, self.last_name, self.display_name)
            ):
                raise ValueError("approved Employee candidate identity is incomplete")
        elif any(
            value is not None
            for value in (
                self.first_name,
                self.last_name,
                self.display_name,
                self.job_title,
            )
        ):
            raise ValueError("excluded identity cannot carry Employee candidate fields")


@dataclass(frozen=True)
class CompletionRequirements:
    customer_lineage: int
    location_identities: int
    location_exceptions: int
    employee_crosswalks: int
    employee_candidates: int
    employee_excluded: int
    note_outcomes: dict[str, int]
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
        history_service: CutoverMigrationService | None = None,
    ) -> None:
        self._customers = customer_service or CustomerAdapterImportService()
        self._operations = operational_service or OperationalMigrationService()
        self._financials = financial_service or FinancialMigrationService()
        self._history = history_service or CutoverMigrationService()

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
        if not REQUIRED_SOURCE4_ENTITIES.issubset(command.supported_entities):
            raise ValueError("master omits a required SOURCE.4 entity domain")
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
        hybrid_admission: HybridCustomerAdmission,
        parent_closure: JobParentClosure,
    ) -> CustomerAdapterImportReport:
        if reviewed.source_system != SOURCE4_SYSTEM:
            raise ValueError("orchestrator requires SOURCE.4 Customer identity")
        hybrid_admission.validate()
        parent_closure.validate()
        async with factory() as session:
            master = await self._active_master(
                session, context=context, master_run_id=master_run_id
            )
            if (
                master.transformation_contracts.get("hybrid_customer_admission_digest")
                != hybrid_admission.digest
            ):
                raise ValueError("master hybrid Customer admission binding mismatch")
            if (
                master.transformation_contracts.get("customer_parent_closure_digest")
                != parent_closure.digest
            ):
                raise ValueError("master Customer parent-closure binding mismatch")
            admissible = {
                item.native_customer_id: item
                for item in hybrid_admission.candidates
                if item.outcome == "PERSISTABLE"
            }
            reviewed_ids = {item.source_identity for item in reviewed.aggregates}
            if reviewed_ids != set(admissible):
                raise ValueError(
                    "reviewed Customer persistence set differs from hybrid admission"
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
            candidate = admissible.get(aggregate.source_identity)
            if candidate is None:
                raise ValueError("persisted Customer lacks hybrid admission evidence")
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
                    source_context={
                        "row_number": aggregate.row_number,
                        **candidate.lineage_context(
                            master.package_digest, hybrid_admission.digest
                        ),
                        "customer_parent_closure_digest": parent_closure.digest,
                    },
                    customer_source_identity_id=identity.id,
                ),
            )

        async def location_lineage(
            session: AsyncSession,
            identity: CustomerSourceIdentity,
            aggregate: ReviewedCustomerAggregate,
            locations: tuple[ServiceLocation, ...],
        ) -> None:
            if len(aggregate.service_location_source_identities) != len(locations):
                raise ValueError("source4_location_identity_count_mismatch")
            candidate = admissible.get(aggregate.source_identity)
            if candidate is None:
                raise ValueError("source4_location_customer_admission_missing")
            address_by_id = {
                item.get("id"): item
                for item in candidate.acquired_payload.get("addresses", [])
            }
            assert context.active_branch is not None
            for source_location_id, location in zip(
                aggregate.service_location_source_identities, locations, strict=True
            ):
                location_id = getattr(location, "id", None)
                customer_id = getattr(location, "customer_id", None)
                if location_id is None or customer_id != identity.customer_id:
                    raise ValueError("source4_location_target_scope_invalid")
                address = address_by_id.get(source_location_id)
                if not isinstance(address, dict):
                    raise TypeError("source4_location_assertion_missing")
                session.add(
                    ServiceLocationSourceIdentity(
                        company_id=context.company.id,
                        branch_id=context.active_branch.id,
                        master_run_id=master_run_id,
                        customer_source_identity_id=identity.id,
                        service_location_id=location_id,
                        customer_id=identity.customer_id,
                        source_system=SOURCE4_SYSTEM,
                        source_location_id=source_location_id,
                        source_digest=canonical_sha256(address),
                        package_digest=master.package_digest,
                        transformation_version=reviewed.schema_version,
                        transformation_digest=reviewed.transformation_sha256,
                        source_context={
                            "assertion": "authoritative_native_location",
                            "ordinal": aggregate.service_location_source_identities.index(
                                source_location_id
                            ),
                        },
                        first_run_id=identity.first_run_id,
                    )
                )
            await session.flush()

        return await self._customers.run(
            factory,
            context=context,
            reviewed=reviewed,
            boundary=boundary,
            master_run_id=master_run_id,
            lineage_callback=lineage,
            location_lineage_callback=location_lineage,
        )

    async def stage_customers(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        reviewed: ReviewedCustomerAdapterOutput,
        hybrid_admission: HybridCustomerAdmission,
    ) -> HybridCustomerStagingReport:
        """Stage the derived hybrid contract after, and only under, its master."""
        master = await self._active_master(
            session, context=context, master_run_id=master_run_id
        )
        reviewed.validate_integrity()
        hybrid_admission.validate()
        if reviewed.source_system != SOURCE4_SYSTEM:
            raise ValueError("protected_staging_source_system_invalid")
        if reviewed.source_sha256 != hybrid_admission.digest:
            raise ValueError("protected_staging_admission_digest_mismatch")
        if (
            master.transformation_contracts.get("hybrid_customer_admission_digest")
            != hybrid_admission.digest
        ):
            raise ValueError("protected_staging_master_binding_mismatch")
        counts = {
            "customers": len(reviewed.aggregates),
            "contacts": sum(
                item.contact_json is not None for item in reviewed.aggregates
            ),
            "locations": sum(
                len(item.service_location_json) for item in reviewed.aggregates
            ),
            "child_exceptions": sum(
                len(item.location_exception_ids) for item in hybrid_admission.candidates
            ),
        }
        staging_digest = canonical_sha256(
            {
                "contract": "hcp-source4-master-bound-customer-staging/v1",
                "master_run_id": str(master_run_id),
                "package_digest": master.package_digest,
                "hybrid_admission_digest": hybrid_admission.digest,
                "review_digest": reviewed.review_sha256,
                "transformation_digest": reviewed.transformation_sha256,
                "company_id": str(context.company.id),
                "branch_id": str(master.branch_id),
                "actor_id": str(context.user.id),
                "counts": counts,
            }
        )
        artifact_id = uuid5(STAGING_NAMESPACE, staging_digest)
        existing = await session.get(CustomerMigrationSourceArtifact, artifact_id)
        if existing is not None:
            if (
                existing.master_run_id != master_run_id
                or existing.staging_digest != staging_digest
                or existing.source_sha256 != hybrid_admission.digest
                or existing.row_count != len(hybrid_admission.candidates)
            ):
                raise ValueError("protected_staging_replay_conflict")
            staged_rows = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
            staged_candidates = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationCandidate)
                .join(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
            staged_exceptions = await session.scalar(
                select(func.count())
                .select_from(CustomerMigrationChildException)
                .join(CustomerMigrationSourceRow)
                .where(CustomerMigrationSourceRow.artifact_id == artifact_id)
            )
            if (
                staged_rows != counts["customers"]
                or staged_candidates
                != counts["customers"] + counts["contacts"] + counts["locations"]
                or staged_exceptions != counts["child_exceptions"]
            ):
                raise ValueError("protected_staging_replay_incomplete")
            return HybridCustomerStagingReport(
                artifact_id, staging_digest, reused=True, **counts
            )
        assert context.active_branch is not None
        artifact = CustomerMigrationSourceArtifact(
            id=artifact_id,
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            source_system=SOURCE4_SYSTEM,
            master_run_id=master_run_id,
            actor_user_id=context.user.id,
            package_digest=master.package_digest,
            hybrid_admission_digest=hybrid_admission.digest,
            staging_digest=staging_digest,
            source_sha256=hybrid_admission.digest,
            schema_version=reviewed.schema_version,
            transformation_sha256=reviewed.transformation_sha256,
            byte_size=0,
            row_count=len(hybrid_admission.candidates),
        )
        session.add(artifact)
        await session.flush()
        candidate_by_id = {
            item.native_customer_id: item for item in hybrid_admission.candidates
        }
        for aggregate in reviewed.aggregates:
            source_row = CustomerMigrationSourceRow(
                artifact_id=artifact.id,
                row_number=aggregate.row_number,
                source_identity=aggregate.source_identity,
                source_id_sha256=aggregate.source_identity_sha256,
                source_row_sha256=aggregate.source_row_sha256,
                disposition="accepted",
            )
            session.add(source_row)
            await session.flush()
            payloads = [
                ("customer", 0, aggregate.customer.model_dump(mode="json")),
                *(
                    [("contact", 0, aggregate.contact.model_dump(mode="json"))]
                    if aggregate.contact is not None
                    else []
                ),
                *[
                    ("service_location", index, location.model_dump(mode="json"))
                    for index, location in enumerate(aggregate.service_locations)
                ],
            ]
            for entity_type, ordinal, payload in payloads:
                session.add(
                    CustomerMigrationCandidate(
                        source_row_id=source_row.id,
                        entity_type=entity_type,
                        ordinal=ordinal,
                        payload_sha256=hashlib.sha256(
                            json.dumps(payload, sort_keys=True).encode()
                        ).hexdigest(),
                        payload=payload,
                    )
                )
            candidate = candidate_by_id[aggregate.source_identity]
            address_by_id = {
                item.get("id"): item
                for item in candidate.acquired_payload.get("addresses", [])
            }
            for ordinal, location_id in enumerate(candidate.location_exception_ids, 1):
                address = address_by_id.get(location_id, {})
                missing = tuple(
                    key
                    for key in ("id", "street", "city", "state", "zip")
                    if not str(address.get(key) or "").strip()
                )
                evidence_digest = canonical_sha256(address)
                session.add(
                    CustomerMigrationChildException(
                        source_row_id=source_row.id,
                        source_id_sha256=canonical_sha256(location_id),
                        source_location_id=location_id
                        if location_id.startswith("adr_")
                        else None,
                        parent_customer_source_id=aggregate.source_identity,
                        package_digest=master.package_digest,
                        transformation_digest=reviewed.transformation_sha256,
                        reconciliation_key=canonical_sha256(
                            {
                                "customer": aggregate.source_identity,
                                "location": location_id,
                            }
                        ),
                        resolution_state="unresolved",
                        contract_version="hcp-source4-location-child-exception/v1",
                        address_group_number=ordinal,
                        missing_fields=list(missing),
                        reason_code="incomplete_authoritative_location",
                        evidence_sha256=evidence_digest,
                    )
                )
        await session.flush()
        return HybridCustomerStagingReport(
            artifact.id, staging_digest, reused=False, **counts
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

    async def run_history(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        notes: tuple[HistoryMigrationRecord, ...],
        resume_run_id: UUID | None = None,
        interrupt_after: int | None = None,
    ) -> MigrationReport:
        async with factory() as session:
            await self._active_master(
                session, context=context, master_run_id=master_run_id
            )
            existing = await session.scalar(
                select(OperationalMigrationRun).where(
                    OperationalMigrationRun.master_run_id == master_run_id,
                    OperationalMigrationRun.master_domain == "history",
                )
            )
            if existing is not None and resume_run_id is None:
                if existing.status not in COMPLETABLE_CHILD_STATUSES:
                    raise ValueError("History child requires explicit resume")
                expected_digest = self._history.source_digest(
                    source_system=SOURCE4_SYSTEM,
                    history=notes,
                    artifacts=(),
                )
                if existing.source_digest != expected_digest:
                    raise ValueError("History replay changed immutable Note evidence")
                return MigrationReport(
                    existing.id,
                    existing.mode,
                    existing.source_count,
                    existing.accepted_count,
                    existing.rejected_count,
                    existing.duplicate_count,
                    existing.unresolved_count,
                )
            if resume_run_id is not None and (
                existing is None or existing.id != resume_run_id
            ):
                raise ValueError("History resume run is outside the active master")
        return await self._history.run(
            factory,
            context=context,
            source_system=SOURCE4_SYSTEM,
            history=notes,
            artifacts=(),
            dry_run=False,
            master_run_id=master_run_id,
            resume_run_id=resume_run_id,
            interrupt_after=interrupt_after,
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

    async def persist_employee_candidate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        command: EmployeeCandidateCommand,
    ) -> tuple[Employee | None, bool]:
        await self._active_master(session, context=context, master_run_id=master_run_id)
        command.validate()
        existing = await session.scalar(
            select(HcpEmployeeSourceCrosswalk).where(
                HcpEmployeeSourceCrosswalk.company_id == context.company.id,
                HcpEmployeeSourceCrosswalk.native_employee_id
                == command.native_employee_id,
                HcpEmployeeSourceCrosswalk.evidence_version == 1,
            )
        )
        employee_id = (
            uuid5(
                EMPLOYEE_NAMESPACE,
                f"{context.company.id}:{command.native_employee_id}",
            )
            if command.disposition == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
            else None
        )
        crosswalk = EmployeeCrosswalkCommand(
            native_employee_id=command.native_employee_id,
            disposition=command.disposition,
            source_digest=command.source_digest,
            owner_receipt_digest=command.owner_receipt_digest,
            employee_id=employee_id,
        )
        if existing is not None:
            if (
                existing.master_run_id != master_run_id
                or existing.evidence_digest != crosswalk.evidence_digest
                or existing.employee_id != employee_id
            ):
                raise ValueError("contradictory Employee source identity persistence")
            employee = (
                await session.get(Employee, existing.employee_id)
                if existing.employee_id is not None
                else None
            )
            if existing.employee_id is not None and employee is None:
                raise ValueError("Employee crosswalk target is missing")
            return employee, False
        if employee_id is None:
            await persist_employee_crosswalk(
                session,
                context=context,
                master_run_id=master_run_id,
                command=crosswalk,
            )
            return None, True
        if await session.get(Employee, employee_id) is not None:
            raise ValueError("deterministic Employee exists without source crosswalk")
        assert context.active_branch is not None
        assert command.first_name is not None
        assert command.last_name is not None
        assert command.display_name is not None
        employee = Employee(
            id=employee_id,
            company_id=context.company.id,
            membership_id=None,
            home_branch_id=context.active_branch.id,
            employee_number=f"HCP-{command.source_digest[:16].upper()}",
            first_name=command.first_name.strip(),
            last_name=command.last_name.strip(),
            display_name=command.display_name.strip(),
            job_title=command.job_title.strip() if command.job_title else None,
            employee_type="employee",
            status="inactive",
            hire_date=None,
            termination_date=None,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        session.add(employee)
        await session.flush()
        await persist_employee_crosswalk(
            session,
            context=context,
            master_run_id=master_run_id,
            command=replace(crosswalk, employee_id=employee.id),
        )
        return employee, True

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
        if customer_run is None or set(by_domain) != {
            "operational",
            "financial",
            "history",
        }:
            raise ValueError("required child migration run is missing")
        child_runs: dict[str, CustomerMigrationRun | OperationalMigrationRun] = {
            "customer": customer_run,
            "operational": by_domain["operational"],
            "financial": by_domain["financial"],
            "history": by_domain["history"],
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
        candidate_count = await session.scalar(
            select(func.count())
            .select_from(HcpEmployeeSourceCrosswalk)
            .where(
                HcpEmployeeSourceCrosswalk.master_run_id == master_run_id,
                HcpEmployeeSourceCrosswalk.disposition
                == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
                HcpEmployeeSourceCrosswalk.employee_id.is_not(None),
            )
        )
        excluded_count = await session.scalar(
            select(func.count())
            .select_from(HcpEmployeeSourceCrosswalk)
            .where(
                HcpEmployeeSourceCrosswalk.master_run_id == master_run_id,
                HcpEmployeeSourceCrosswalk.disposition
                == "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
                HcpEmployeeSourceCrosswalk.employee_id.is_(None),
            )
        )
        unlinked_count = await session.scalar(
            select(func.count())
            .select_from(UnlinkedEstimateEvidence)
            .where(
                UnlinkedEstimateEvidence.master_run_id == master_run_id,
                UnlinkedEstimateEvidence.synthetic_qualification.is_(False),
            )
        )
        location_identity_count = await session.scalar(
            select(func.count())
            .select_from(ServiceLocationSourceIdentity)
            .where(ServiceLocationSourceIdentity.master_run_id == master_run_id)
        )
        location_exception_count = await session.scalar(
            select(func.count())
            .select_from(CustomerMigrationChildException)
            .join(CustomerMigrationSourceRow)
            .join(CustomerMigrationSourceArtifact)
            .where(CustomerMigrationSourceArtifact.master_run_id == master_run_id)
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
        if (
            candidate_count != requirements.employee_candidates
            or excluded_count != requirements.employee_excluded
            or employee_count != candidate_count + excluded_count
        ):
            raise ValueError("Employee candidate/exclusion accounting is incomplete")
        if (
            location_identity_count != requirements.location_identities
            or location_exception_count != requirements.location_exceptions
        ):
            raise ValueError(
                "Service Location identity/exception accounting is incomplete"
            )
        history = by_domain["history"]
        actual_note_outcomes = {
            "persisted": history.accepted_count,
            "duplicate": history.duplicate_count,
            "exception": history.unresolved_count,
            "rejected": history.rejected_count,
        }
        if actual_note_outcomes != requirements.note_outcomes:
            raise ValueError("Note/history reconciliation is incomplete")
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
