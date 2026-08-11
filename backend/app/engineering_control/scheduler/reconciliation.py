from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_capacity.models import (
    EngineeringCapacityAllocation,
    EngineeringCapacityEvent,
    EngineeringCapacityMachine,
    EngineeringCapacityReservation,
    EngineeringWorkerCapacity,
)
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringMilestoneEvent,
    EngineeringRoadmap,
)
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.registry import (
    EngineeringRepositoryRegistryError,
    engineering_repository_registry,
)
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.worker_control.models import EngineeringWorker
from app.worker_identity.models import WorkerCredential, WorkerIdentity

from .manifest import SchedulerManifest, load_scheduler_manifest
from .models import (
    EngineeringCapacityBinding,
    EngineeringPermanentCapacity,
    EngineeringSchedulerEvent,
    EngineeringSchedulerSnapshot,
)
from .schemas import (
    CapacityFinding,
    Classification,
    CRM2PreservationEvidence,
    ProposedTransition,
    RecordClassification,
    SchedulerReconciliationReport,
)


class SchedulerReconciliationError(RuntimeError):
    pass


class SchedulerReconciliationService:
    """Build a deterministic, zero-write comparison of durable state to MMQ truth."""

    inventory_models: ClassVar[dict[str, type[Any]]] = {
        "roadmaps": EngineeringRoadmap,
        "milestones": EngineeringMilestone,
        "commands": EngineeringCommand,
        "workstream_runtimes": EngineeringWorkstreamRuntime,
        "reservations": EngineeringCapacityReservation,
        "allocations": EngineeringCapacityAllocation,
        "milestone_events": EngineeringMilestoneEvent,
        "capacity_events": EngineeringCapacityEvent,
        "worker_capacities": EngineeringWorkerCapacity,
        "permanent_capacities": EngineeringPermanentCapacity,
        "capacity_bindings": EngineeringCapacityBinding,
    }

    async def dry_run(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        manifest: SchedulerManifest | None = None,
    ) -> SchedulerReconciliationReport:
        contract = manifest or load_scheduler_manifest()
        before = {
            name: int(
                await session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.company_id == company_id)
                )
                or 0
            )
            for name, model in self.inventory_models.items()
        }
        scheduler_roadmap_exists = bool(
            await session.scalar(
                select(EngineeringRoadmap.id).where(
                    EngineeringRoadmap.company_id == company_id,
                    EngineeringRoadmap.title == "MMQ.5 Production Scheduler",
                )
            )
        )
        milestones = tuple(
            (
                await session.scalars(
                    select(EngineeringMilestone).where(
                        EngineeringMilestone.company_id == company_id
                    )
                )
            ).all()
        )
        runtimes = tuple(
            (
                await session.scalars(
                    select(EngineeringWorkstreamRuntime).where(
                        EngineeringWorkstreamRuntime.company_id == company_id
                    )
                )
            ).all()
        )
        reservations = tuple(
            (
                await session.scalars(
                    select(EngineeringCapacityReservation).where(
                        EngineeringCapacityReservation.company_id == company_id
                    )
                )
            ).all()
        )
        allocations = tuple(
            (
                await session.scalars(
                    select(EngineeringCapacityAllocation).where(
                        EngineeringCapacityAllocation.company_id == company_id
                    )
                )
            ).all()
        )
        capacities = tuple(
            (
                await session.scalars(
                    select(EngineeringWorkerCapacity).where(
                        EngineeringWorkerCapacity.company_id == company_id
                    )
                )
            ).all()
        )
        milestone_events = tuple(
            (
                await session.scalars(
                    select(EngineeringMilestoneEvent).where(
                        EngineeringMilestoneEvent.company_id == company_id
                    )
                )
            ).all()
        )
        capacity_events = tuple(
            (
                await session.scalars(
                    select(EngineeringCapacityEvent).where(
                        EngineeringCapacityEvent.company_id == company_id
                    )
                )
            ).all()
        )
        permanent = tuple(
            (
                await session.scalars(
                    select(EngineeringPermanentCapacity).where(
                        EngineeringPermanentCapacity.company_id == company_id
                    )
                )
            ).all()
        )
        bindings = tuple(
            (
                await session.scalars(
                    select(EngineeringCapacityBinding).where(
                        EngineeringCapacityBinding.company_id == company_id
                    )
                )
            ).all()
        )
        machines = tuple(
            (
                await session.scalars(
                    select(EngineeringCapacityMachine).where(
                        EngineeringCapacityMachine.company_id == company_id
                    )
                )
            ).all()
        )
        workers = tuple(
            (
                await session.scalars(
                    select(EngineeringWorker).where(
                        EngineeringWorker.company_id == company_id
                    )
                )
            ).all()
        )
        identities = tuple(
            (
                await session.scalars(
                    select(WorkerIdentity).where(
                        WorkerIdentity.company_id == company_id
                    )
                )
            ).all()
        )
        credentials = tuple(
            (
                await session.scalars(
                    select(WorkerCredential).where(
                        WorkerCredential.company_id == company_id
                    )
                )
            ).all()
        )

        classifications: list[RecordClassification] = []
        transitions: list[ProposedTransition] = []
        matched_ids: set[UUID] = set()
        title_frequency = Counter(item.title for item in milestones)
        by_code = {
            item.milestone_code: item for item in milestones if item.milestone_code
        }
        durable_status = {
            "planned": "planned",
            "ready": "ready",
            "in_progress": "running",
            "waiting_for_owner_review": "waiting_review",
            "complete": "completed",
            "blocked": "blocked",
            "reconciliation_required": "blocked",
        }

        for definition in contract.milestones:
            exact = by_code.get(definition.milestone_code)
            legacy = [
                item for item in milestones if item.title in definition.legacy_titles
            ]
            candidate = exact or (legacy[0] if len(legacy) == 1 else None)
            if candidate is None:
                if definition.preserve_active_execution and legacy:
                    classification = "ambiguous"
                    reason = "CRM.2-like durable records are ambiguous; creation is prohibited."
                else:
                    classification = "reconciliation-required"
                    reason = "No durable milestone has this stable code; an auditable upsert is proposed."
                transitions.append(
                    ProposedTransition(
                        record_type="milestone",
                        milestone_code=definition.milestone_code,
                        to_state=definition.readiness_state,
                        reason=reason,
                    )
                )
                continue
            matched_ids.add(candidate.id)
            if exact is None and title_frequency[candidate.title] != 1:
                classification = "ambiguous"
                reason = "Title-only legacy identity is not unique and cannot establish completion or adoption."
            elif (
                definition.milestone_code == "CRM.2"
                and candidate.command_id is not None
                and candidate.status in {"ready", "running", "paused", "waiting_review"}
            ):
                classification = "reconciliation-required"
                reason = (
                    "Authoritative Git records CRM.2 complete, but its durable command is "
                    "nonterminal; owner disposition is required before scheduler adoption."
                )
            elif (
                definition.preserve_active_execution
                and candidate.command_id is not None
            ):
                classification = "current/adoptable"
                reason = "A unique CRM.2 milestone and command can adopt scheduler metadata without changing execution state."
            elif definition.preserve_active_execution:
                classification = "reconciliation-required"
                reason = "CRM.2 requires exact command/runtime/capacity adoption before metadata mutation."
            elif definition.readiness_state == "complete":
                classification = "completed"
                reason = "Manifest contains explicit completion evidence independent of the legacy title."
            else:
                classification = "current/adoptable"
                reason = "A unique durable record can adopt the stable scheduler identity without deleting history."
            classifications.append(
                RecordClassification(
                    record_type="milestone",
                    record_id=candidate.id,
                    classification=cast(Classification, classification),
                    milestone_code=definition.milestone_code,
                    reason=reason,
                )
            )
            expected_readiness = (
                "waiting_for_owner_review"
                if definition.preserve_active_execution
                and candidate.status == "waiting_review"
                else "in_progress"
                if definition.preserve_active_execution
                and candidate.command_id is not None
                else definition.readiness_state
            )
            expected_status = (
                candidate.status
                if definition.preserve_active_execution
                and candidate.command_id is not None
                else durable_status[definition.readiness_state]
            )
            needs_update = bool(
                candidate.milestone_code != definition.milestone_code
                or candidate.scheduler_fingerprint != contract.fingerprint
                or candidate.readiness_state != expected_readiness
                or candidate.reconciliation_state != "current"
                or candidate.status != expected_status
            )
            if (
                classification not in {"ambiguous", "reconciliation-required"}
                and needs_update
                and (
                    not definition.preserve_active_execution
                    or candidate.command_id is not None
                )
            ):
                transitions.append(
                    ProposedTransition(
                        record_type="milestone",
                        record_id=candidate.id,
                        milestone_code=definition.milestone_code,
                        from_state=candidate.status,
                        to_state=(
                            "in_progress"
                            if definition.preserve_active_execution
                            else definition.readiness_state
                        ),
                        reason=(
                            "Adopt CRM.2 scheduler metadata only; preserve its execution and capacity chain."
                            if definition.preserve_active_execution
                            else "Adopt stable MMQ metadata and authoritative scheduler state with an audit event."
                        ),
                    )
                )

        manifest_legacy_titles = {
            title
            for definition in contract.milestones
            for title in definition.legacy_titles
        }
        for item in milestones:
            if item.id in matched_ids:
                continue
            if item.command_id is not None and item.status in {
                "ready",
                "running",
                "paused",
            }:
                classification = "orphaned"
                reason = "Nonterminal command-linked milestone is absent from the current scheduler manifest."
            elif item.title in manifest_legacy_titles:
                classification = "ambiguous"
                reason = "Additional record shares a legacy title and requires owner reconciliation."
            else:
                classification = "superseded"
                reason = "Legacy roadmap history is retained but is not current scheduler truth."
            classifications.append(
                RecordClassification(
                    record_type="milestone",
                    record_id=item.id,
                    classification=cast(Classification, classification),
                    milestone_code=item.milestone_code,
                    reason=reason,
                )
            )

        matched_milestone_by_command = {
            item.command_id: item
            for item in milestones
            if item.id in matched_ids and item.command_id is not None
        }
        command_ids = {
            item.id
            for item in (
                await session.scalars(
                    select(EngineeringCommand).where(
                        EngineeringCommand.company_id == company_id
                    )
                )
            ).all()
        }
        for command_id in sorted(command_ids, key=str):
            milestone = matched_milestone_by_command.get(command_id)
            classifications.append(
                RecordClassification(
                    record_type="command",
                    record_id=command_id,
                    classification=("current/adoptable" if milestone else "orphaned"),
                    milestone_code=milestone.milestone_code if milestone else None,
                    reason=(
                        "Command is linked to a uniquely identified current/adoptable milestone."
                        if milestone
                        else "Command has no uniquely identified current scheduler milestone."
                    ),
                )
            )
        for runtime in runtimes:
            milestone = matched_milestone_by_command.get(runtime.command_id)
            classifications.append(
                RecordClassification(
                    record_type="workstream_runtime",
                    record_id=runtime.id,
                    classification=("current/adoptable" if milestone else "orphaned"),
                    milestone_code=milestone.milestone_code if milestone else None,
                    reason=(
                        "Runtime belongs to a uniquely identified scheduler command."
                        if milestone
                        else "Runtime command is not attached to current scheduler truth."
                    ),
                )
            )
        for record_type, records in (
            ("reservation", reservations),
            ("allocation", allocations),
        ):
            for record in records:
                milestone = matched_milestone_by_command.get(record.command_id)
                classifications.append(
                    RecordClassification(
                        record_type=record_type,
                        record_id=record.id,
                        classification=(
                            "current/adoptable" if milestone else "orphaned"
                        ),
                        milestone_code=milestone.milestone_code if milestone else None,
                        reason=(
                            "Capacity record belongs to a uniquely identified scheduler command."
                            if milestone
                            else "Capacity record has no current scheduler command identity."
                        ),
                    )
                )
        code_by_milestone_id = {
            item.id: item.milestone_code
            for item in milestones
            if item.id in matched_ids
        }
        for milestone_event in milestone_events:
            classifications.append(
                RecordClassification(
                    record_type="milestone_event",
                    record_id=milestone_event.id,
                    classification=(
                        "current/adoptable"
                        if milestone_event.milestone_id in code_by_milestone_id
                        else "superseded"
                    ),
                    milestone_code=code_by_milestone_id.get(
                        milestone_event.milestone_id
                    ),
                    reason="Historical event is retained append-only.",
                )
            )
        for capacity_event in capacity_events:
            classifications.append(
                RecordClassification(
                    record_type="capacity_event",
                    record_id=capacity_event.id,
                    classification="current/adoptable",
                    reason="Capacity history is retained append-only for worker-binding review.",
                )
            )
        for capacity in capacities:
            classifications.append(
                RecordClassification(
                    record_type="worker_capacity",
                    record_id=capacity.id,
                    classification=(
                        "current/adoptable"
                        if capacity.health_state == "healthy"
                        and capacity.operational_state
                        in {"available", "reserved", "occupied"}
                        else "reconciliation-required"
                    ),
                    reason=(
                        "Configured worker capacity is operational and healthy."
                        if capacity.health_state == "healthy"
                        and capacity.operational_state
                        in {"available", "reserved", "occupied"}
                        else f"Capacity is {capacity.operational_state}/{capacity.health_state}; no health promotion is proposed."
                    ),
                )
            )

        runtime_by_command = {item.command_id: item for item in runtimes}
        crm_milestones = tuple(
            item
            for item in milestones
            if item.milestone_code == "CRM.2"
            or item.title in {"CRM.2", "Close launch CRM gaps"}
        )
        crm_command_ids = tuple(
            sorted(
                {item.command_id for item in crm_milestones if item.command_id}, key=str
            )
        )
        crm_runtime_ids = tuple(
            runtime_by_command[item].id
            for item in crm_command_ids
            if item in runtime_by_command
        )
        crm_reservations = tuple(
            item for item in reservations if item.command_id in crm_command_ids
        )
        crm_allocations = tuple(
            item for item in allocations if item.command_id in crm_command_ids
        )
        crm_capacity_ids = tuple(
            sorted(
                {item.worker_capacity_id for item in crm_reservations}
                | {item.worker_capacity_id for item in crm_allocations},
                key=str,
            )
        )
        proposed_mutation_ids = tuple(
            item.record_id
            for item in transitions
            if item.record_id is not None
            and (
                item.record_id in {milestone.id for milestone in crm_milestones}
                or item.record_id in crm_command_ids
            )
        )
        protected_mutation_ids = set(crm_command_ids) | set(crm_runtime_ids)
        protected_mutation_ids |= {item.id for item in crm_reservations}
        protected_mutation_ids |= {item.id for item in crm_allocations}
        protected_mutation_ids |= set(crm_capacity_ids)
        protected_mutation_detected = bool(
            set(proposed_mutation_ids) & protected_mutation_ids
        )
        crm = CRM2PreservationEvidence(
            milestone_ids=tuple(sorted((item.id for item in crm_milestones), key=str)),
            command_ids=crm_command_ids,
            runtime_ids=tuple(sorted(crm_runtime_ids, key=str)),
            reservation_ids=tuple(
                sorted((item.id for item in crm_reservations), key=str)
            ),
            allocation_ids=tuple(
                sorted((item.id for item in crm_allocations), key=str)
            ),
            worker_capacity_ids=crm_capacity_ids,
            proposed_mutation_ids=proposed_mutation_ids,
            preserved=not protected_mutation_detected,
            reason=(
                "Dry-run may adopt CRM.2 milestone metadata but proposes no mutation to its execution/capacity chain."
                if not protected_mutation_detected
                else "A protected CRM.2 execution/capacity mutation was detected; APPLY must fail closed."
            ),
        )

        binding_by_capacity = {
            item.permanent_capacity_id: item
            for item in bindings
            if item.state == "active"
        }
        permanent_by_code = {item.identity_code: item for item in permanent}
        capacity_by_id = {item.id: item for item in capacities}
        machine_by_id = {item.id: item for item in machines}
        worker_by_id = {item.id: item for item in workers}
        identity_by_worker = {
            item.orchestration_worker_id: item
            for item in identities
            if item.orchestration_worker_id is not None
        }
        credential_by_identity = {
            item.identity_id: item for item in credentials if item.state == "active"
        }
        capacity_findings: list[CapacityFinding] = []
        for capacity_definition in contract.capacities:
            identity = permanent_by_code.get(capacity_definition.identity)
            binding = binding_by_capacity.get(identity.id) if identity else None
            worker_capacity = (
                capacity_by_id.get(binding.worker_capacity_id) if binding else None
            )
            machine = (
                machine_by_id.get(worker_capacity.machine_id)
                if worker_capacity
                else None
            )
            worker = (
                worker_by_id.get(worker_capacity.worker_id) if worker_capacity else None
            )
            worker_identity = identity_by_worker.get(worker.id) if worker else None
            credential = (
                credential_by_identity.get(worker_identity.id)
                if worker_identity
                else None
            )
            repository_valid = True
            try:
                repository = engineering_repository_registry.resolve("acp-enterprise")
                repository_valid = (
                    repository.approved_active_branch == "customer-management-v1"
                )
            except EngineeringRepositoryRegistryError:
                repository_valid = False
            if identity is None:
                state, reason = (
                    "unmapped",
                    "Permanent capacity identity is not present in durable state.",
                )
            elif binding is None:
                state, reason = (
                    "reconciliation_required",
                    "No active auditable worker-capacity binding exists.",
                )
            elif worker_capacity is None:
                state, reason = (
                    "reconciliation_required",
                    "Binding references unavailable worker capacity.",
                )
            elif machine is None or machine.enrollment_state != "enrolled":
                state, reason = (
                    "reconciliation_required",
                    "Worker capacity has no enrolled machine mapping.",
                )
            elif worker is None or worker.lifecycle_state not in {
                "available",
                "leased",
            }:
                state, reason = (
                    "reconciliation_required",
                    "Bound worker is absent or not operationally active.",
                )
            elif worker_identity is None or worker_identity.state != "active":
                state, reason = (
                    "reconciliation_required",
                    "Bound worker has no active durable identity.",
                )
            elif credential is None or credential.expires_at <= datetime.now(
                timezone.utc
            ):
                state, reason = (
                    "reconciliation_required",
                    "Bound worker has no active unexpired credential.",
                )
            elif worker.last_heartbeat_at is None or datetime.now(
                timezone.utc
            ) - worker.last_heartbeat_at > timedelta(minutes=2):
                state, reason = (
                    "reconciliation_required",
                    "Bound worker heartbeat is stale.",
                )
            elif "engineering.execute" not in worker.capabilities:
                state, reason = (
                    "reconciliation_required",
                    "Bound worker lacks engineering execution capability.",
                )
            elif not repository_valid:
                state, reason = (
                    "reconciliation_required",
                    "Enterprise repository/branch is not authorized by the repository registry.",
                )
            elif worker_capacity.configured_limit < 1:
                state, reason = (
                    "reconciliation_required",
                    "Configured concurrency is unavailable.",
                )
            elif worker_capacity.operational_state not in {
                "available",
                "reserved",
                "occupied",
            }:
                state, reason = (
                    "reconciliation_required",
                    f"Configured capacity operational state is {worker_capacity.operational_state}.",
                )
            elif worker_capacity.health_state != "healthy":
                state, reason = (
                    "reconciliation_required",
                    f"Configured capacity health is {worker_capacity.health_state}; it was not promoted to healthy.",
                )
            else:
                state, reason = (
                    "current",
                    "Active binding points to healthy configured worker capacity.",
                )
            capacity_findings.append(
                CapacityFinding(
                    permanent_capacity_identity=capacity_definition.identity,
                    binding_id=binding.id if binding else None,
                    worker_capacity_id=worker_capacity.id if worker_capacity else None,
                    state=state,
                    reason=reason,
                )
            )

        proposed_after = dict(before)
        if not scheduler_roadmap_exists:
            proposed_after["roadmaps"] += 1
        proposed_after["permanent_capacities"] = max(
            before["permanent_capacities"], len(contract.capacities)
        )
        proposed_after["milestones"] += sum(
            item.record_id is None and item.record_type == "milestone"
            for item in transitions
        )
        orphaned = tuple(
            sorted(
                (
                    item.record_id
                    for item in classifications
                    if item.classification == "orphaned"
                ),
                key=str,
            )
        )
        ambiguous = tuple(
            sorted(
                (
                    item.record_id
                    for item in classifications
                    if item.classification == "ambiguous"
                ),
                key=str,
            )
        )
        destructive = sum(item.destructive for item in transitions)
        return SchedulerReconciliationReport(
            mode="dry_run",
            scheduler_version=contract.scheduler_version,
            scheduler_fingerprint=contract.fingerprint,
            before_counts=before,
            proposed_after_counts=proposed_after,
            classifications=tuple(
                sorted(
                    classifications,
                    key=lambda item: (item.record_type, str(item.record_id)),
                )
            ),
            proposed_transitions=tuple(
                sorted(
                    transitions,
                    key=lambda item: (
                        item.record_type,
                        item.milestone_code or "",
                        str(item.record_id or ""),
                    ),
                )
            ),
            capacity_mappings=tuple(capacity_findings),
            crm2_preservation=crm,
            orphaned_record_ids=orphaned,
            ambiguous_record_ids=ambiguous,
            destructive_operation_count=destructive,
            mutations_performed=0,
        )

    async def apply(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        actor_user_id: UUID,
        checkpoint_2_authorized: bool = False,
    ) -> SchedulerReconciliationReport:
        """Idempotently apply non-destructive metadata after explicit Checkpoint 2 authority."""
        if not checkpoint_2_authorized:
            raise SchedulerReconciliationError(
                "APPLY requires explicit Checkpoint 2 authorization."
            )
        contract = load_scheduler_manifest()
        report = await self.dry_run(session, company_id=company_id, manifest=contract)
        if report.destructive_operation_count:
            raise SchedulerReconciliationError(
                "Destructive scheduler operations are prohibited."
            )
        if not report.crm2_preservation.preserved:
            raise SchedulerReconciliationError(
                "CRM.2 cannot be preserved unambiguously."
            )
        if report.ambiguous_record_ids:
            raise SchedulerReconciliationError(
                "Ambiguous durable records require owner reconciliation."
            )
        crm_definition = next(
            item for item in contract.milestones if item.milestone_code == "CRM.2"
        )
        crm_candidates = tuple(
            (
                await session.scalars(
                    select(EngineeringMilestone).where(
                        EngineeringMilestone.company_id == company_id,
                        (
                            (EngineeringMilestone.milestone_code == "CRM.2")
                            | (
                                EngineeringMilestone.title.in_(
                                    crm_definition.legacy_titles
                                )
                            )
                        ),
                    )
                )
            ).all()
        )
        if len(crm_candidates) > 1:
            raise SchedulerReconciliationError(
                "CRM.2 durable identity is not singular; APPLY fails closed."
            )
        if (
            crm_candidates
            and crm_candidates[0].command_id is not None
            and crm_candidates[0].status
            in {"ready", "running", "paused", "waiting_review"}
        ):
            raise SchedulerReconciliationError(
                "CRM.2 has a nonterminal durable command; owner reconciliation is required before APPLY."
            )

        now = datetime.now(timezone.utc)
        mutations = 0
        await session.rollback()
        async with session.begin():
            snapshot = await session.scalar(
                select(EngineeringSchedulerSnapshot).where(
                    EngineeringSchedulerSnapshot.company_id == company_id,
                    EngineeringSchedulerSnapshot.scheduler_version
                    == contract.scheduler_version,
                )
            )
            if snapshot is None:
                active = tuple(
                    (
                        await session.scalars(
                            select(EngineeringSchedulerSnapshot).where(
                                EngineeringSchedulerSnapshot.company_id == company_id,
                                EngineeringSchedulerSnapshot.active.is_(True),
                            )
                        )
                    ).all()
                )
                for item in active:
                    item.active = False
                    item.version += 1
                snapshot = EngineeringSchedulerSnapshot(
                    company_id=company_id,
                    scheduler_version=contract.scheduler_version,
                    fingerprint=contract.fingerprint,
                    manifest=contract.model_dump(mode="json"),
                    source_documents=list(contract.source_documents),
                    active=True,
                    activated_at=now,
                )
                session.add(snapshot)
                mutations += 1

            for capacity_definition in contract.capacities:
                capacity = await session.scalar(
                    select(EngineeringPermanentCapacity).where(
                        EngineeringPermanentCapacity.company_id == company_id,
                        EngineeringPermanentCapacity.identity_code
                        == capacity_definition.identity,
                    )
                )
                if capacity is None:
                    capacity = EngineeringPermanentCapacity(
                        company_id=company_id,
                        identity_code=capacity_definition.identity,
                        display_name=capacity_definition.display_name,
                        state="unavailable",
                        reconciliation_reason="Worker binding requires separate owner-reviewed evidence.",
                    )
                    session.add(capacity)
                    mutations += 1

            roadmap = await session.scalar(
                select(EngineeringRoadmap).where(
                    EngineeringRoadmap.company_id == company_id,
                    EngineeringRoadmap.title == "MMQ.5 Production Scheduler",
                )
            )
            if roadmap is None:
                roadmap = EngineeringRoadmap(
                    company_id=company_id,
                    title="MMQ.5 Production Scheduler",
                    repository_key="acp-enterprise",
                    expected_branch="customer-management-v1",
                    expected_head=str(
                        next(
                            item.starting_commit_evidence.get("commit")
                            for item in contract.milestones
                            if item.milestone_code == "PLAT.1"
                        )
                    ),
                    status="active",
                )
                session.add(roadmap)
                await session.flush()
                mutations += 1
            max_position = int(
                await session.scalar(
                    select(func.max(EngineeringMilestone.position)).where(
                        EngineeringMilestone.roadmap_id == roadmap.id
                    )
                )
                or 0
            )
            status_map = {
                "planned": "planned",
                "ready": "ready",
                "in_progress": "running",
                "waiting_for_owner_review": "waiting_review",
                "complete": "completed",
                "blocked": "blocked",
                "reconciliation_required": "blocked",
            }
            for definition in contract.milestones:
                matches = tuple(
                    (
                        await session.scalars(
                            select(EngineeringMilestone).where(
                                EngineeringMilestone.company_id == company_id,
                                (
                                    (
                                        EngineeringMilestone.milestone_code
                                        == definition.milestone_code
                                    )
                                    | (
                                        EngineeringMilestone.title.in_(
                                            definition.legacy_titles
                                        )
                                    )
                                ),
                            )
                        )
                    ).all()
                )
                unique = {item.id: item for item in matches}
                if len(unique) > 1:
                    raise SchedulerReconciliationError(
                        f"{definition.milestone_code} has ambiguous durable identities."
                    )
                milestone = next(iter(unique.values()), None)
                if definition.preserve_active_execution:
                    if milestone is None or milestone.command_id is None:
                        raise SchedulerReconciliationError(
                            "CRM.2 preservation evidence changed during APPLY."
                        )
                    if milestone.status not in {"running", "paused", "waiting_review"}:
                        raise SchedulerReconciliationError(
                            "CRM.2 is not in a preservable active or review state."
                        )
                    expected_crm_readiness = (
                        "waiting_for_owner_review"
                        if milestone.status == "waiting_review"
                        else "in_progress"
                    )
                    if (
                        milestone.scheduler_fingerprint == contract.fingerprint
                        and milestone.reconciliation_state == "current"
                        and milestone.readiness_state == expected_crm_readiness
                    ):
                        continue
                    milestone.milestone_code = definition.milestone_code
                    milestone.scheduler_version = contract.scheduler_version
                    milestone.scheduler_fingerprint = contract.fingerprint
                    milestone.permanent_capacity_identity = (
                        definition.permanent_capacity_identity
                    )
                    milestone.implementation_classification = (
                        definition.implementation_classification
                    )
                    milestone.integration_checkpoint = definition.integration_checkpoint
                    milestone.starting_commit_rule = definition.starting_commit_rule
                    milestone.starting_commit_evidence = (
                        definition.starting_commit_evidence
                    )
                    milestone.migration_classification = (
                        definition.migration_classification
                    )
                    milestone.shared_contract_classification = (
                        definition.shared_contract_classification
                    )
                    milestone.readiness_state = expected_crm_readiness
                    milestone.dependency_evidence = [
                        item.model_dump(mode="json")
                        for item in definition.dependency_evidence
                    ]
                    milestone.reconciliation_state = "current"
                    milestone.version += 1
                    milestone.updated_at = now
                    crm_event_key = (
                        f"scheduler:{contract.scheduler_version}:milestone:CRM.2"
                    )
                    crm_event = await session.scalar(
                        select(EngineeringSchedulerEvent).where(
                            EngineeringSchedulerEvent.company_id == company_id,
                            EngineeringSchedulerEvent.idempotency_key == crm_event_key,
                        )
                    )
                    if crm_event is None:
                        session.add(
                            EngineeringSchedulerEvent(
                                company_id=company_id,
                                event_type="scheduler.active_milestone_adopted",
                                scheduler_version=contract.scheduler_version,
                                milestone_code="CRM.2",
                                permanent_capacity_identity="OM2",
                                record_id=milestone.id,
                                details={
                                    "metadata_only": True,
                                    "command_id": str(milestone.command_id),
                                    "execution_chain_preserved": True,
                                },
                                actor_user_id=actor_user_id,
                                idempotency_key=crm_event_key,
                            )
                        )
                    mutations += 1
                    continue
                if (
                    milestone is not None
                    and milestone.scheduler_fingerprint == contract.fingerprint
                    and milestone.readiness_state == definition.readiness_state
                    and milestone.reconciliation_state == "current"
                    and milestone.status == status_map[definition.readiness_state]
                ):
                    continue
                if milestone is None:
                    max_position += 1
                    milestone = EngineeringMilestone(
                        company_id=company_id,
                        roadmap_id=roadmap.id,
                        position=max_position,
                        title=definition.title,
                        objective=definition.title,
                        owning_workstream=definition.workstream,
                        owning_branch="customer-management-v1",
                        authority=[definition.owner_checkpoint],
                        constraints=[
                            "Start only from authoritative durable scheduler truth."
                        ],
                        dependencies=[
                            item.milestone_code
                            for item in definition.dependency_evidence
                        ],
                        validation=[
                            "Validate the manifest-defined milestone boundary."
                        ],
                        deliverables=list(definition.completion_evidence)
                        or [definition.title],
                        stop_conditions=["Stop at the recorded owner checkpoint."],
                        expected_completion_evidence=list(
                            definition.completion_evidence
                        ),
                        status=status_map[definition.readiness_state],
                        definition_approved=definition.readiness_state
                        in {"ready", "complete"},
                        requested_code_changes=definition.implementation_classification
                        != "TYPE_C",
                    )
                    session.add(milestone)
                    await session.flush()
                    mutations += 1
                milestone.milestone_code = definition.milestone_code
                milestone.scheduler_version = contract.scheduler_version
                milestone.scheduler_fingerprint = contract.fingerprint
                milestone.permanent_capacity_identity = (
                    definition.permanent_capacity_identity
                )
                milestone.implementation_classification = (
                    definition.implementation_classification
                )
                milestone.integration_checkpoint = definition.integration_checkpoint
                milestone.starting_commit_rule = definition.starting_commit_rule
                milestone.starting_commit_evidence = definition.starting_commit_evidence
                milestone.migration_classification = definition.migration_classification
                milestone.shared_contract_classification = (
                    definition.shared_contract_classification
                )
                milestone.readiness_state = definition.readiness_state
                milestone.dependency_evidence = [
                    item.model_dump(mode="json")
                    for item in definition.dependency_evidence
                ]
                milestone.reconciliation_state = "current"
                milestone.status = status_map[definition.readiness_state]
                milestone.version += 1
                milestone.updated_at = now
                event = await session.scalar(
                    select(EngineeringSchedulerEvent).where(
                        EngineeringSchedulerEvent.company_id == company_id,
                        EngineeringSchedulerEvent.idempotency_key
                        == f"scheduler:{contract.scheduler_version}:milestone:{definition.milestone_code}",
                    )
                )
                if event is None:
                    session.add(
                        EngineeringSchedulerEvent(
                            company_id=company_id,
                            event_type="scheduler.milestone_reconciled",
                            scheduler_version=contract.scheduler_version,
                            milestone_code=definition.milestone_code,
                            permanent_capacity_identity=definition.permanent_capacity_identity,
                            record_id=milestone.id,
                            details={
                                "non_destructive": True,
                                "prior_history_preserved": True,
                            },
                            actor_user_id=actor_user_id,
                            idempotency_key=f"scheduler:{contract.scheduler_version}:milestone:{definition.milestone_code}",
                        )
                    )
                mutations += 1
        result = await self.dry_run(session, company_id=company_id, manifest=contract)
        return result.model_copy(
            update={"mode": "apply", "mutations_performed": mutations}
        )


scheduler_reconciliation_service = SchedulerReconciliationService()
