import fnmatch
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.records import EngineeringApprovalState
from app.engineering_control.repository_operation.errors import (
    RepositoryOperationGitError,
)
from app.engineering_control.repository_operation.git_adapter import (
    ProductionBoundedGitAdapter,
)
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.engineering_execution.contracts import (
    EngineeringExecutionState,
    EngineeringExecutionStatus,
)
from app.engineering_execution.models import EngineeringExecution
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.execution_nodes.models import ProviderExecutionTransition
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from app.worker_control.contracts import (
    AuthenticatedWorkerContext,
    ExecutionOffer,
    WorkerCapability,
    WorkerLeaseStatus,
)
from app.worker_control.models import EngineeringWorker, WorkerLease
from app.worker_control.service import WorkerControlService
from app.worker_control.transport.contracts import WorkerSession

from .contracts import (
    ControlledCommandType,
    ControlledExecutionOffer,
    ControlledExecutionResult,
    ControlledOfferState,
    ControlledOutcome,
    immutable_mapping,
)
from .errors import (
    ControlledExecutionConflictError,
    ControlledExecutionIneligibleError,
    ControlledExecutionNotFoundError,
    ControlledExecutionPayloadError,
)
from .models import ControlledExecutionOfferModel, ControlledExecutionResultModel
from .repository import ControlledExecutionRepository

SAFE_WORKSPACE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
SAFE_ERROR = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
MAX_OUTPUT_BYTES = 128_000
MAX_VALIDATION_RUNS = 32
MAX_VALIDATION_TEXT = 20_000
SENSITIVE_EVIDENCE_MARKERS = (
    "authorization:",
    "bearer ",
    "private key",
    "password=",
    "token=",
    "secret=",
    "npm_auth_token",
)


def _evidence_set(value: object) -> frozenset[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return frozenset(value)


def calculate_adoption_evidence_digest(
    *,
    command_id: UUID,
    execution_id: UUID,
    ecid: str,
    offer_id: UUID,
    lease_id: UUID,
    starting_head: str,
    commit_sha: str,
    commit_parent: str,
    remote_head: str,
    boundary_version: int,
    boundary_fingerprint: str,
    boundary_digest: str,
    provider_completed_at: datetime,
    workspace_clean: bool,
    output: dict[str, object],
) -> str:
    payload = {
        "command_id": str(command_id),
        "execution_id": str(execution_id),
        "ecid": ecid,
        "offer_id": str(offer_id),
        "lease_id": str(lease_id),
        "starting_head": starting_head,
        "commit_sha": commit_sha,
        "commit_parent": commit_parent,
        "remote_head": remote_head,
        "boundary_version": boundary_version,
        "boundary_fingerprint": boundary_fingerprint,
        "boundary_digest": boundary_digest,
        "provider_completed_at": provider_completed_at.isoformat(),
        "workspace_clean": workspace_clean,
        "output": output,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_validation_run(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("skipped") is True:
        return (
            set(value) == {"identity", "skipped", "passed"}
            and isinstance(value.get("identity"), str)
            and value.get("passed") is True
        )
    expected = {
        "identity",
        "argv",
        "working_directory",
        "started_at",
        "completed_at",
        "duration_ms",
        "exit_code",
        "passed",
        "failure_summary",
        "toolchain",
        "stdout",
        "stderr",
    }
    if set(value) != expected:
        return False
    argv = value.get("argv")
    if (
        not isinstance(value.get("identity"), str)
        or not isinstance(argv, list)
        or not argv
        or len(argv) > 64
        or any(not isinstance(item, str) or len(item) > 500 for item in argv)
        or not isinstance(value.get("working_directory"), str)
        or (
            value.get("working_directory") != "."
            and not _safe_relative_path(str(value.get("working_directory")))
        )
        or not isinstance(value.get("duration_ms"), int)
        or not isinstance(value.get("exit_code"), int)
        or not isinstance(value.get("passed"), bool)
        or (
            value.get("failure_summary") is not None
            and (
                not isinstance(value.get("failure_summary"), str)
                or len(str(value.get("failure_summary"))) > 2_000
                or any(
                    marker in str(value.get("failure_summary")).casefold()
                    for marker in SENSITIVE_EVIDENCE_MARKERS
                )
            )
        )
        or not isinstance(value.get("toolchain"), dict)
        or len(json.dumps(value.get("toolchain"), sort_keys=True)) > 4_000
        or any(
            marker in json.dumps(value.get("toolchain"), sort_keys=True).casefold()
            for marker in SENSITIVE_EVIDENCE_MARKERS
        )
    ):
        return False
    for name in ("stdout", "stderr"):
        stream = value.get(name)
        if (
            not isinstance(stream, dict)
            or set(stream) != {"text", "truncated", "redacted"}
            or not isinstance(stream.get("text"), str)
            or len(stream["text"].encode()) > MAX_VALIDATION_TEXT
            or any(
                marker in stream["text"].casefold()
                for marker in SENSITIVE_EVIDENCE_MARKERS
            )
            or not isinstance(stream.get("truncated"), bool)
            or not isinstance(stream.get("redacted"), bool)
        ):
            return False
    return True


def _valid_failed_output(output: dict[str, object]) -> bool:
    if set(output) == {
        "workspace_id",
        "repository_key",
        "branch",
        "starting_head",
        "rejection_stage",
        "provider_status_code",
        "repository_mutated",
    }:
        return bool(
            output.get("repository_mutated") is False
            and output.get("rejection_stage")
            in {"provider_admission", "workspace_preparation"}
            and isinstance((status_code := output.get("provider_status_code")), int)
            and 400 <= status_code < 500
        )
    expected = {
        "workspace_id",
        "repository_key",
        "branch",
        "starting_head",
        "file_count",
        "file_boundary",
        "validation",
        "validation_runs",
        "validation_environment",
        "implementation_summary",
        "repository_mutated",
    }
    boundary = output.get("file_boundary")
    validation = output.get("validation")
    runs = output.get("validation_runs")
    return bool(
        set(output) == expected
        and output.get("repository_mutated") is False
        and isinstance(output.get("file_count"), int)
        and isinstance(boundary, list)
        and output.get("file_count") == len(boundary)
        and len(boundary) <= 500
        and all(
            isinstance(item, str) and len(item) <= 500 and _safe_relative_path(item)
            for item in boundary
        )
        and boundary == sorted(set(boundary))
        and isinstance(validation, dict)
        and validation
        and all(
            isinstance(name, str) and isinstance(passed, bool)
            for name, passed in validation.items()
        )
        and any(passed is False for passed in validation.values())
        and isinstance(runs, list)
        and 0 < len(runs) <= MAX_VALIDATION_RUNS
        and all(_valid_validation_run(run) for run in runs)
        and isinstance(output.get("validation_environment"), dict)
        and len(json.dumps(output.get("validation_environment"), sort_keys=True))
        <= 4_000
        and not any(
            marker
            in json.dumps(
                output.get("validation_environment"), sort_keys=True
            ).casefold()
            for marker in SENSITIVE_EVIDENCE_MARKERS
        )
        and isinstance(output.get("implementation_summary"), str)
        and len(str(output.get("implementation_summary"))) <= 8_000
        and not any(
            marker in str(output.get("implementation_summary")).casefold()
            for marker in SENSITIVE_EVIDENCE_MARKERS
        )
    )


class ControlledExecutionService:
    def __init__(
        self,
        *,
        repository: type[ControlledExecutionRepository] = ControlledExecutionRepository,
        workers: WorkerControlService | None = None,
        authorization: AuthorizationService = authorization_service,
        events: type[BusinessEventService] = BusinessEventService,
        audit: AuditService = audit_service,
        publication_adapter: ProductionBoundedGitAdapter | None = None,
    ) -> None:
        self.repository = repository
        self.workers = workers or WorkerControlService()
        self.authorization = authorization
        self.events = events
        self.audit = audit
        self.publication_adapter = publication_adapter

    async def adopt_expired_result(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        execution_id: UUID,
        command_id: UUID,
        ecid: str,
        offer_id: UUID,
        lease_id: UUID,
        starting_head: str,
        commit_sha: str,
        commit_parent: str,
        remote_head: str,
        boundary_version: int,
        boundary_fingerprint: str,
        boundary_digest: str,
        provider_completed_at: datetime,
        provider_evidence_digest: str,
        workspace_clean: bool,
        output: dict[str, object],
        idempotency_key: str,
        now: datetime | None = None,
    ) -> tuple[ControlledExecutionResult, UUID, datetime]:
        """Adopt immutable published evidence without reviving expired authority."""
        self.authorization.require_permission(
            context, EngineeringCommandPermission.APPROVE
        )
        adopted_at = now or utc_now()
        calculated_digest = calculate_adoption_evidence_digest(
            command_id=command_id,
            execution_id=execution_id,
            ecid=ecid,
            offer_id=offer_id,
            lease_id=lease_id,
            starting_head=starting_head,
            commit_sha=commit_sha,
            commit_parent=commit_parent,
            remote_head=remote_head,
            boundary_version=boundary_version,
            boundary_fingerprint=boundary_fingerprint,
            boundary_digest=boundary_digest,
            provider_completed_at=provider_completed_at,
            workspace_clean=workspace_clean,
            output=output,
        )
        if calculated_digest != provider_evidence_digest:
            raise ControlledExecutionPayloadError(
                "Provider evidence digest does not match immutable evidence."
            )
        files = output.get("file_boundary")
        if not isinstance(files, list) or not all(
            isinstance(path, str) for path in files
        ):
            raise ControlledExecutionPayloadError(
                "Publication path evidence is invalid."
            )
        try:
            publication = self._publication_adapter()
            commit = publication.inspect_commit(commit_sha)
            current_authoritative_head = publication.verify_historical_publication(
                str(output.get("branch", "")), commit_sha
            )
        except RepositoryOperationGitError as error:
            raise ControlledExecutionPayloadError(
                "Authoritative publication proof could not be verified."
            ) from error
        if (
            commit.parent != commit_parent
            or commit.files != tuple(files)
            or remote_head != commit_sha
        ):
            raise ControlledExecutionPayloadError(
                "Authoritative publication proof does not match provider evidence."
            )
        try:
            async with session.begin():
                offer = await self.repository.get_offer_for_update(
                    session, company_id=context.company.id, offer_id=offer_id
                )
                command = await session.get(EngineeringCommand, command_id)
                execution = await session.get(EngineeringExecution, execution_id)
                if (
                    offer is None
                    or command is None
                    or execution is None
                    or command.company_id != context.company.id
                    or execution.company_id != context.company.id
                    or offer.execution_id != execution_id
                    or offer.command_id != command_id
                    or offer.lease_id != lease_id
                    or execution.command_id != command_id
                    or command.ecid != ecid
                ):
                    raise ControlledExecutionNotFoundError(
                        "Controlled execution lineage was not found."
                    )
                existing = await session.scalar(
                    select(ControlledExecutionResultModel).where(
                        ControlledExecutionResultModel.company_id == context.company.id,
                        ControlledExecutionResultModel.offer_id == offer_id,
                    )
                )
                if existing is not None:
                    adoption = existing.output.get("adoption")
                    if (
                        isinstance(adoption, dict)
                        and adoption.get("idempotency_key") == idempotency_key
                        and adoption.get("evidence_digest") == provider_evidence_digest
                    ):
                        result = self.repository.result_record(existing)
                        stored_adopted_at = adoption.get("adopted_at")
                        if isinstance(stored_adopted_at, str):
                            adopted_at = datetime.fromisoformat(stored_adopted_at)
                    else:
                        raise ControlledExecutionConflictError(
                            "A conflicting terminal result already exists."
                        )
                else:
                    boundary, boundary_provenance = (
                        await self._resolve_adoption_boundary(
                            session,
                            command=command,
                            execution=execution,
                            starting_head=starting_head,
                            boundary_version=boundary_version,
                            boundary_fingerprint=boundary_fingerprint,
                        )
                    )
                    self._validate_adoption_source(
                        command=command,
                        execution=execution,
                        offer=offer,
                        boundary=boundary,
                        starting_head=starting_head,
                        commit_sha=commit_sha,
                        commit_parent=commit_parent,
                        remote_head=remote_head,
                        boundary_version=boundary_version,
                        boundary_fingerprint=boundary_fingerprint,
                        boundary_digest=boundary_digest,
                        provider_completed_at=provider_completed_at,
                        workspace_clean=workspace_clean,
                        output=output,
                    )
                    from app.engineering_control.mobile.roadmaps import (
                        EngineeringMilestone,
                    )

                    milestone = await session.scalar(
                        select(EngineeringMilestone).where(
                            EngineeringMilestone.company_id == context.company.id,
                            EngineeringMilestone.command_id == command_id,
                        )
                    )
                    if milestone is None:
                        raise ControlledExecutionIneligibleError(
                            "Scheduler lineage is unavailable for adoption."
                        )
                    adopted_output = {
                        **output,
                        "adoption": {
                            "evidence_digest": provider_evidence_digest,
                            "idempotency_key": idempotency_key,
                            "provider_completed_at": provider_completed_at.isoformat(),
                            "adopted_at": adopted_at.isoformat(),
                            "adopted_by_user_id": str(context.user.id),
                            "transport_failure_preserved": True,
                            "expired_lease_preserved": str(lease_id),
                            "historical_publication_head": commit_sha,
                            "current_authoritative_head_at_adoption": (
                                current_authoritative_head
                            ),
                            "prior_reconciliation_evidence": dict(
                                execution.evidence_summary
                            ),
                            "boundary_evidence": boundary_provenance,
                        },
                    }
                    result = await self.repository.create_adopted_result(
                        session,
                        offer=offer,
                        output=adopted_output,
                        started_at=execution.started_at
                        or offer.acquired_at
                        or provider_completed_at,
                        completed_at=provider_completed_at,
                        adopted_at=adopted_at,
                    )
                    execution.state = EngineeringExecutionState.COMPLETED.value
                    execution.status = EngineeringExecutionStatus.SUCCEEDED.value
                    execution.evidence_summary = adopted_output
                    execution.validation_summary = {
                        "controlled_execution": True,
                        "repository_mutated": True,
                        "required": dict(cast(dict[str, bool], output["validation"])),
                        "runs": list(
                            cast(list[dict[str, object]], output["validation_runs"])
                        ),
                        "owner_authorized_adoption": True,
                    }
                    execution.failure_classification = None
                    execution.finished_at = provider_completed_at
                    execution.updated_at = adopted_at
                    execution.version += 1
                    runtime = await session.scalar(
                        select(EngineeringWorkstreamRuntime).where(
                            EngineeringWorkstreamRuntime.company_id
                            == context.company.id,
                            EngineeringWorkstreamRuntime.command_id == command_id,
                        )
                    )
                    if runtime is not None:
                        runtime.runtime_state = "completed"
                        runtime.worker_health = "healthy"
                        runtime.progress_percent = 100
                        runtime.current_activity = (
                            "Published result ready for owner review"
                        )
                        runtime.reason_code = None
                        runtime.updated_at = adopted_at
                        runtime.version += 1
                    self._stage(
                        session,
                        offer=_offer_record(offer),
                        event_type=EventType.ENGINEERING_CONTROLLED_RESULT_ADOPTED,
                        now=adopted_at,
                        result_id=result.id,
                        repository_mutated=True,
                    )
                    self.audit.stage(
                        session,
                        AuditEntry(
                            action="engineering.controlled_result_adopted",
                            resource_type="engineering_execution",
                            actor_user_id=context.user.id,
                            company_id=context.company.id,
                            branch_id=(
                                context.active_branch.id
                                if context.active_branch
                                else None
                            ),
                            resource_id=execution_id,
                            correlation_id=execution.correlation_id,
                            details={
                                "ecid": ecid,
                                "command_id": str(command_id),
                                "offer_id": str(offer_id),
                                "lease_id": str(lease_id),
                                "result_id": str(result.id),
                                "commit_sha": commit_sha,
                                "evidence_digest": provider_evidence_digest,
                                "transport_failure_preserved": True,
                                "boundary_evidence": boundary_provenance,
                            },
                            occurred_at=adopted_at,
                        ),
                    )
            review = await EngineeringReviewService().prepare(
                session, context=context, command_id=command_id, now=adopted_at
            )
            return result, review.review.id, adopted_at
        except IntegrityError as error:
            await session.rollback()
            raise ControlledExecutionConflictError(
                "Evidence adoption conflicts with an existing terminal result."
            ) from error

    def _publication_adapter(self) -> ProductionBoundedGitAdapter:
        if self.publication_adapter is not None:
            return self.publication_adapter
        root = settings.repository_operation_root
        if root is None or not root.strip():
            raise ControlledExecutionPayloadError(
                "Controlled repository publication verification is unavailable."
            )
        self.publication_adapter = ProductionBoundedGitAdapter(Path(root))
        return self.publication_adapter

    @staticmethod
    async def _resolve_adoption_boundary(
        session: AsyncSession,
        *,
        command: EngineeringCommand,
        execution: EngineeringExecution,
        starting_head: str,
        boundary_version: int,
        boundary_fingerprint: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Resolve modern frozen metadata or one historically bound legacy source."""
        boundary = dict(command.execution_boundary)
        canonical_digest = hashlib.sha256(
            json.dumps(boundary, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if canonical_digest != command.execution_boundary_digest:
            raise ControlledExecutionPayloadError(
                "Frozen command boundary digest is inconsistent."
            )
        stored_version = boundary.get("boundary_version")
        stored_fingerprint = boundary.get("fingerprint")
        if stored_version is not None or stored_fingerprint is not None:
            if (
                stored_version != boundary_version
                or stored_fingerprint != boundary_fingerprint
            ):
                raise ControlledExecutionPayloadError(
                    "Frozen command boundary metadata is incomplete or contradictory."
                )
            return boundary, {
                "source": "frozen_command",
                "command_id": str(command.id),
                "boundary_version": boundary_version,
                "boundary_fingerprint": boundary_fingerprint,
            }

        # Legacy composition is deliberately restricted to immutable scheduler
        # snapshots and their pre-command reconciliation event. The live milestone
        # definition is mutable current-readiness state and is never a source.
        from app.engineering_control.mobile.roadmaps import (
            EngineeringMilestone,
            EngineeringRoadmap,
        )
        from app.engineering_control.scheduler.manifest import SchedulerManifest
        from app.engineering_control.scheduler.models import (
            EngineeringSchedulerEvent,
            EngineeringSchedulerSnapshot,
        )

        milestones = tuple(
            (
                await session.scalars(
                    select(EngineeringMilestone).where(
                        EngineeringMilestone.company_id == command.company_id,
                        EngineeringMilestone.command_id == command.id,
                    )
                )
            ).all()
        )
        if len(milestones) != 1 or milestones[0].milestone_code is None:
            raise ControlledExecutionPayloadError(
                "Legacy scheduler boundary lineage is unavailable or ambiguous."
            )
        milestone = milestones[0]
        roadmap = await session.get(EngineeringRoadmap, milestone.roadmap_id)
        if (
            roadmap is None
            or roadmap.company_id != command.company_id
            or roadmap.repository_key != command.repository_key
            or roadmap.expected_branch != command.expected_branch
            or milestone.owning_branch != command.expected_branch
            or execution.command_id != command.id
            or command.expected_head != starting_head
        ):
            raise ControlledExecutionPayloadError(
                "Legacy scheduler boundary identity does not match execution lineage."
            )

        cutoff = command.approved_at or command.created_at
        events = tuple(
            (
                await session.scalars(
                    select(EngineeringSchedulerEvent).where(
                        EngineeringSchedulerEvent.company_id == command.company_id,
                        EngineeringSchedulerEvent.record_id == milestone.id,
                        EngineeringSchedulerEvent.milestone_code
                        == milestone.milestone_code,
                        EngineeringSchedulerEvent.event_type
                        == "scheduler.milestone_reconciled",
                        EngineeringSchedulerEvent.occurred_at <= cutoff,
                    )
                )
            ).all()
        )
        candidates: list[
            tuple[
                EngineeringSchedulerSnapshot,
                EngineeringSchedulerEvent,
                dict[str, object],
            ]
        ] = []
        for event in events:
            if event.occurred_at > cutoff:
                continue
            snapshot = await session.scalar(
                select(EngineeringSchedulerSnapshot).where(
                    EngineeringSchedulerSnapshot.company_id == command.company_id,
                    EngineeringSchedulerSnapshot.scheduler_version
                    == event.scheduler_version,
                    EngineeringSchedulerSnapshot.created_at <= cutoff,
                )
            )
            if snapshot is None or (
                snapshot.activated_at is not None and snapshot.activated_at > cutoff
            ):
                continue
            try:
                manifest = SchedulerManifest.model_validate(snapshot.manifest)
            except ValueError:
                continue
            if (
                manifest.scheduler_version != snapshot.scheduler_version
                or manifest.fingerprint != snapshot.fingerprint
            ):
                continue
            definitions = tuple(
                item
                for item in manifest.milestones
                if item.milestone_code == milestone.milestone_code
            )
            if len(definitions) != 1:
                continue
            definition = definitions[0]
            evidence_head = definition.starting_commit_evidence.get(
                "authoritative_head"
            )
            definition_boundary = definition.execution_boundary
            if (
                definition.workstream != milestone.owning_workstream
                or definition.repository_key != command.repository_key
                or evidence_head != starting_head
                or definition_boundary is None
                or definition_boundary.boundary_version != boundary_version
                or definition_boundary.fingerprint != boundary_fingerprint
            ):
                continue
            composed = {
                **boundary,
                "boundary_version": definition_boundary.boundary_version,
                "fingerprint": definition_boundary.fingerprint,
            }
            if (
                boundary.get("allowed_repository") != command.repository_key
                or boundary.get("allowed_branch") != command.expected_branch
                or boundary.get("expected_head") != starting_head
                or _evidence_set(boundary.get("allowed_paths"))
                != frozenset(definition_boundary.allowed_paths)
                or _evidence_set(boundary.get("forbidden_paths"))
                != frozenset(definition_boundary.forbidden_paths)
                or _evidence_set(boundary.get("permitted_operations"))
                != frozenset(definition_boundary.permitted_operations)
                or _evidence_set(boundary.get("validation_requirements"))
                != frozenset(definition_boundary.validation_requirements)
            ):
                continue
            candidates.append((snapshot, event, composed))

        if not candidates:
            raise ControlledExecutionPayloadError(
                "No immutable historical scheduler boundary matches this execution."
            )
        identities = {
            json.dumps(item[2], sort_keys=True, separators=(",", ":"))
            for item in candidates
        }
        if len(identities) != 1:
            raise ControlledExecutionPayloadError(
                "Historical scheduler boundary evidence is contradictory."
            )
        snapshot, event, composed = max(
            candidates, key=lambda item: (item[1].occurred_at, str(item[1].id))
        )
        return cast(dict[str, object], composed), {
            "source": "legacy_scheduler_snapshot",
            "command_id": str(command.id),
            "execution_id": str(execution.id),
            "milestone_id": str(milestone.id),
            "milestone_code": milestone.milestone_code,
            "workstream": milestone.owning_workstream,
            "repository_key": command.repository_key,
            "expected_branch": command.expected_branch,
            "starting_head": starting_head,
            "scheduler_snapshot_id": str(snapshot.id),
            "scheduler_event_id": str(event.id),
            "scheduler_version": snapshot.scheduler_version,
            "scheduler_fingerprint": snapshot.fingerprint,
            "snapshot_created_at": snapshot.created_at.isoformat(),
            "event_occurred_at": event.occurred_at.isoformat(),
            "boundary_version": boundary_version,
            "boundary_fingerprint": boundary_fingerprint,
            "command_boundary_unchanged": True,
        }

    @staticmethod
    def _validate_adoption_source(
        *,
        command: EngineeringCommand,
        execution: EngineeringExecution,
        offer: ControlledExecutionOfferModel,
        boundary: dict[str, object] | None = None,
        starting_head: str,
        commit_sha: str,
        commit_parent: str,
        remote_head: str,
        boundary_version: int,
        boundary_fingerprint: str,
        boundary_digest: str,
        provider_completed_at: datetime,
        workspace_clean: bool,
        output: dict[str, object],
    ) -> None:
        boundary = dict(boundary or command.execution_boundary)
        files = output.get("file_boundary")
        validation = output.get("validation")
        runs = output.get("validation_runs")
        evidence = output.get("evidence")
        requirements = boundary.get("validation_requirements")
        allowed_paths = boundary.get("allowed_paths")
        forbidden_paths = boundary.get("forbidden_paths")
        if (
            offer.state != ControlledOfferState.EXPIRED.value
            or execution.state not in {"running", "starting", "queued"}
            or execution.evidence_summary.get("reconciliation_required") is not True
            or execution.evidence_summary.get("reconciliation_reason")
            != "expired_lease_unresolved_provider_outcome"
            or execution.evidence_summary.get("security_incident") is True
            or command.expected_head != starting_head
            or commit_parent != starting_head
            or commit_sha != remote_head
            or command.execution_boundary_digest != boundary_digest
            or boundary.get("boundary_version") != boundary_version
            or boundary.get("fingerprint") != boundary_fingerprint
            or workspace_clean is not True
            or output.get("repository_mutated") is not True
            or output.get("starting_head") != starting_head
            or output.get("head") != commit_sha
            or output.get("commit_sha") != commit_sha
            or output.get("published_commit_sha") != commit_sha
            or output.get("remote_head_before") != starting_head
            or not isinstance(files, list)
            or files != sorted(set(files))
            or output.get("file_count") != len(files)
            or not isinstance(validation, dict)
            or not isinstance(requirements, list)
            or set(validation) != set(requirements)
            or not validation
            or not all(value is True for value in validation.values())
            or not isinstance(runs, list)
            or len(runs) != len(validation)
            or not all(_valid_validation_run(run) for run in runs)
            or not isinstance(evidence, dict)
            or not isinstance(allowed_paths, list)
            or not isinstance(forbidden_paths, list)
            or evidence.get("phases")
            != [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
            or provider_completed_at < (execution.started_at or provider_completed_at)
        ):
            raise ControlledExecutionPayloadError(
                "Immutable terminal evidence is incomplete or inconsistent."
            )
        allowed = tuple(str(item) for item in allowed_paths)
        forbidden = tuple(str(item) for item in forbidden_paths)
        for path in files:
            if (
                not isinstance(path, str)
                or not _safe_relative_path(path)
                or any(fnmatch.fnmatchcase(path, pattern) for pattern in forbidden)
                or not any(fnmatch.fnmatchcase(path, pattern) for pattern in allowed)
            ):
                raise ControlledExecutionPayloadError(
                    "Adopted result violates the frozen execution boundary."
                )

    async def prepare_offer(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        execution_id: UUID,
        workspace_id: str,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> ControlledExecutionOffer:
        self._require(context)
        occurred_at = now or utc_now()
        workspace = workspace_id.strip().lower()
        if SAFE_WORKSPACE.fullmatch(workspace) is None:
            raise ControlledExecutionPayloadError("Workspace identifier is invalid.")
        if not 30 <= lease_seconds <= 900:
            raise ControlledExecutionPayloadError("Lease duration is invalid.")
        try:
            async with session.begin():
                source = await self.repository.load_authoritative_source(
                    session,
                    company_id=context.company.id,
                    execution_id=execution_id,
                )
                if source is None:
                    raise ControlledExecutionNotFoundError(
                        "Engineering Execution was not found."
                    )
                command, execution = source
                if (
                    command.approval_state != EngineeringApprovalState.APPROVED.value
                    or command.expires_at <= occurred_at
                    or command.canceled_at is not None
                    or command.requested_code_changes
                ):
                    raise ControlledExecutionIneligibleError(
                        "Engineering Command is not eligible for read-only execution."
                    )
                if (
                    execution.state
                    != EngineeringExecutionState.EXECUTION_NOT_CONNECTED.value
                ):
                    raise ControlledExecutionIneligibleError(
                        "Engineering Execution is not eligible for an offer."
                    )
                offer = await self.repository.create_offer(
                    session,
                    company_id=context.company.id,
                    command_id=command.id,
                    execution_id=execution.id,
                    correlation_id=execution.correlation_id,
                    workspace_id=workspace,
                    payload={
                        "manifest_name": "workspace-manifest.json",
                        "expected_branch": command.expected_branch,
                        "expected_head": command.expected_head,
                        "repository_key": command.repository_key,
                        "repository_mutation_allowed": False,
                    },
                    expires_at=min(
                        command.expires_at,
                        occurred_at + timedelta(seconds=lease_seconds),
                    ),
                    lease_seconds=lease_seconds,
                    now=occurred_at,
                )
                self._stage(
                    session,
                    offer=offer,
                    event_type=EventType.ENGINEERING_CONTROLLED_OFFER_CREATED,
                    now=occurred_at,
                )
            return offer
        except IntegrityError as error:
            await session.rollback()
            raise ControlledExecutionConflictError(
                "A controlled offer already exists for this execution."
            ) from error

    async def poll(
        self,
        database: AsyncSession,
        *,
        session: WorkerSession,
        limit: int,
    ) -> tuple[ExecutionOffer, ...]:
        if WorkerCapability.ENGINEERING_EXECUTE not in session.capabilities:
            return ()
        await self.reconcile_acknowledged_code_commands(
            database, worker_session=session
        )
        await self.reject_stale_available_offers_in_transaction(
            database,
            worker_context=session.context,
            now=utc_now(),
        )
        offers = await self.repository.list_available(
            database,
            company_id=session.context.company_id,
            worker_id=session.context.worker_id,
            session_id=session.session_id,
            now=utc_now(),
            limit=limit,
        )
        responses: list[ExecutionOffer] = []
        for offer in offers:
            recovery: dict[str, object] = {}
            if offer.state is ControlledOfferState.ACQUIRED and offer.lease_id:
                if offer.session_id != session.session_id:
                    attached = await self.repository.reattach_acquired_session(
                        database,
                        company_id=session.context.company_id,
                        offer_id=offer.id,
                        worker_id=session.context.worker_id,
                        session_id=session.session_id,
                        now=utc_now(),
                    )
                    if attached is None:
                        continue
                    offer = attached
                lease = await database.get(WorkerLease, offer.lease_id)
                if lease is None or lease.status != "active":
                    continue
                recovery = {
                    "recovery_lease_id": str(lease.id),
                    "recovery_lease_version": lease.version,
                    "recovery_lease_expires_at": lease.expires_at.isoformat(),
                }
            responses.append(
                ExecutionOffer(
                    offer_id=offer.id,
                    execution_id=offer.execution_id,
                    correlation_id=offer.correlation_id,
                    capability_required=offer.capability_required,
                    lease_duration=timedelta(seconds=offer.lease_seconds),
                    expires_at=offer.expires_at,
                    metadata=immutable_mapping(
                        {
                            "command_id": str(offer.command_id),
                            "workspace_id": offer.workspace_id,
                            "command_type": offer.command_type.value,
                            **recovery,
                            **offer.payload,
                        }
                    ),
                )
            )
        return tuple(responses)

    async def reject_stale_available_offers_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        now: datetime,
    ) -> int:
        """Terminally reject stale code offers before any lease can be allocated."""
        rows = (
            await database.execute(
                select(
                    ControlledExecutionOfferModel,
                    EngineeringExecution,
                    EngineeringMilestone,
                    EngineeringRoadmap,
                    EngineeringWorkstreamRuntime,
                )
                .join(
                    EngineeringExecution,
                    EngineeringExecution.id == ControlledExecutionOfferModel.execution_id,
                )
                .join(
                    EngineeringMilestone,
                    EngineeringMilestone.command_id == ControlledExecutionOfferModel.command_id,
                )
                .join(
                    EngineeringRoadmap,
                    EngineeringRoadmap.id == EngineeringMilestone.roadmap_id,
                )
                .outerjoin(
                    EngineeringWorkstreamRuntime,
                    EngineeringWorkstreamRuntime.command_id
                    == ControlledExecutionOfferModel.command_id,
                )
                .where(
                    ControlledExecutionOfferModel.company_id
                    == worker_context.company_id,
                    ControlledExecutionOfferModel.state
                    == ControlledOfferState.AVAILABLE.value,
                    ControlledExecutionOfferModel.command_type
                    == ControlledCommandType.EXECUTE_CODE.value,
                )
                .with_for_update(
                    of=(ControlledExecutionOfferModel, EngineeringExecution),
                    skip_locked=True,
                )
            )
        ).all()
        from app.engineering_control.repository_readiness import readiness_is_current

        rejected = 0
        for offer, execution, milestone, roadmap, runtime in rows:
            if readiness_is_current(
                dict(milestone.starting_commit_evidence),
                repository_key=str(offer.payload.get("repository_key", "")),
                branch=str(offer.payload.get("expected_branch", "")),
                candidate_head=str(offer.payload.get("expected_head", "")),
                worker_id=worker_context.worker_id,
                now=now,
            ) and roadmap.expected_head == offer.payload.get("expected_head"):
                continue
            offer.state = ControlledOfferState.EXPIRED.value
            offer.completed_at = now
            offer.updated_at = now
            offer.version += 1
            execution.state = EngineeringExecutionState.FAILED.value
            execution.status = EngineeringExecutionStatus.FAILED.value
            execution.failure_classification = "controlled_execution_failed"
            execution.finished_at = now
            execution.evidence_summary = {
                **dict(execution.evidence_summary),
                "terminal_rejection": True,
                "rejection_stage": "offer_acquisition_revalidation",
                "rejection_reason": "stale_authoritative_repository_head",
                "repository_mutated": False,
            }
            execution.updated_at = now
            execution.version += 1
            if runtime is not None:
                runtime.runtime_state = "failed"
                runtime.reason_code = "stale_authoritative_repository_head"
                runtime.current_activity = "Execution base changed before acquisition"
                runtime.updated_at = now
                runtime.version += 1
            rejected += 1
        await database.flush()
        return rejected

    async def reconcile_expired_worker_leases_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        now: datetime,
    ) -> int:
        """Quarantine unresolved acquired work after its lease expires.

        Lease expiry is not terminal outcome evidence. The authenticated heartbeat
        provides the existing maintenance cadence, so this closes stale dispatch
        authority and records reconciliation truth without replaying or fabricating
        a result.
        """
        rows = (
            await database.execute(
                select(
                    ControlledExecutionOfferModel,
                    WorkerLease,
                    EngineeringExecution,
                    EngineeringWorkstreamRuntime,
                    EngineeringWorker,
                )
                .join(
                    WorkerLease,
                    WorkerLease.id == ControlledExecutionOfferModel.lease_id,
                )
                .join(
                    EngineeringExecution,
                    EngineeringExecution.id
                    == ControlledExecutionOfferModel.execution_id,
                )
                .outerjoin(
                    EngineeringWorkstreamRuntime,
                    EngineeringWorkstreamRuntime.command_id
                    == ControlledExecutionOfferModel.command_id,
                )
                .join(EngineeringWorker, EngineeringWorker.id == WorkerLease.worker_id)
                .where(
                    ControlledExecutionOfferModel.company_id
                    == worker_context.company_id,
                    ControlledExecutionOfferModel.state
                    == ControlledOfferState.ACQUIRED.value,
                    WorkerLease.status == WorkerLeaseStatus.ACTIVE.value,
                    WorkerLease.expires_at <= now,
                )
                .with_for_update(
                    of=(
                        ControlledExecutionOfferModel,
                        WorkerLease,
                        EngineeringExecution,
                        EngineeringWorker,
                    )
                )
            )
        ).all()
        for offer, lease, execution, runtime, worker in rows:
            offer.state = ControlledOfferState.EXPIRED.value
            offer.completed_at = now
            offer.updated_at = now
            offer.version += 1
            await self.workers.repository.finish_lease(
                database,
                lease=lease,
                worker=worker,
                status=WorkerLeaseStatus.EXPIRED,
                occurred_at=now,
            )
            execution.evidence_summary = {
                **dict(execution.evidence_summary),
                "reconciliation_required": True,
                "reconciliation_reason": "expired_lease_unresolved_provider_outcome",
                "expired_lease_id": str(lease.id),
            }
            execution.updated_at = now
            execution.version += 1
            if runtime is not None and runtime.runtime_state not in {
                "completed",
                "failed",
                "cancelled",
            }:
                runtime.runtime_state = "recovering"
                runtime.worker_health = "degraded"
                runtime.reason_code = "reconciliation_required"
                runtime.current_activity = "Execution outcome requires reconciliation"
                runtime.updated_at = now
                runtime.version += 1
        await database.flush()
        return len(rows)

    async def reconcile_acknowledged_code_commands(
        self, database: AsyncSession, *, worker_session: WorkerSession
    ) -> int:
        occurred_at = utc_now()
        created = 0
        node_id = await self.repository.active_node_id(
            database,
            company_id=worker_session.context.company_id,
            worker_id=worker_session.context.worker_id,
            now=occurred_at,
        )
        if node_id is None:
            return 0
        sources = await self.repository.list_acknowledged_code_executions(
            database,
            company_id=worker_session.context.company_id,
            worker_id=worker_session.context.worker_id,
            now=occurred_at,
            limit=1,
        )
        for command, execution in sources:
            readiness_source = await self.repository.acquisition_readiness(
                database,
                company_id=command.company_id,
                command_id=command.id,
            )
            if readiness_source is None:
                continue
            milestone, roadmap = readiness_source
            from app.engineering_control.repository_readiness import (
                readiness_is_current,
            )

            if (
                roadmap.expected_head != command.expected_head
                or not readiness_is_current(
                    dict(milestone.starting_commit_evidence),
                    repository_key=command.repository_key,
                    branch=command.expected_branch,
                    candidate_head=command.expected_head,
                    worker_id=worker_session.context.worker_id,
                    now=occurred_at,
                )
            ):
                execution.state = EngineeringExecutionState.FAILED.value
                execution.status = EngineeringExecutionStatus.FAILED.value
                execution.failure_classification = "controlled_execution_failed"
                execution.finished_at = occurred_at
                execution.evidence_summary = {
                    **dict(execution.evidence_summary),
                    "terminal_rejection": True,
                    "rejection_stage": "automatic_offer_admission",
                    "rejection_reason": "stale_authoritative_repository_head",
                    "repository_mutated": False,
                }
                execution.updated_at = occurred_at
                execution.version += 1
                runtime = await database.scalar(
                    select(EngineeringWorkstreamRuntime).where(
                        EngineeringWorkstreamRuntime.company_id == command.company_id,
                        EngineeringWorkstreamRuntime.command_id == command.id,
                    )
                )
                if runtime is not None:
                    runtime.runtime_state = "failed"
                    runtime.reason_code = "stale_authoritative_repository_head"
                    runtime.current_activity = (
                        "Execution base changed before worker dispatch"
                    )
                    runtime.updated_at = occurred_at
                    runtime.version += 1
                continue
            boundary = dict(command.execution_boundary)
            mutation_allowed = command.requested_code_changes
            operations = set(
                _evidence_set(boundary.get("permitted_operations")) or ()
            )
            if mutation_allowed:
                required_operations = {
                    "inspect", "modify", "validate", "commit",
                    "mechanical_reconcile", "push",
                }
                capability_profile = "code_change"
            else:
                required_operations = {"inspect", "validate"}
                capability_profile = "inspect_validate_only"
            if operations != required_operations:
                continue
            offer = await self.repository.create_offer(
                database,
                company_id=command.company_id,
                command_id=command.id,
                execution_id=execution.id,
                correlation_id=execution.correlation_id,
                workspace_id=f"execution-{execution.id}",
                command_type=ControlledCommandType.EXECUTE_CODE,
                payload={
                    "node_id": str(node_id),
                    "company_id": str(command.company_id),
                    "command_id": str(command.id),
                    "execution_id": str(execution.id),
                    "repository_key": command.repository_key,
                    "expected_branch": command.expected_branch,
                    "expected_head": command.expected_head,
                    "instruction": command.owner_instruction,
                    "instruction_digest": command.instruction_digest,
                    "request_digest": command.request_digest,
                    "boundary": boundary,
                    "boundary_digest": command.execution_boundary_digest,
                    "commit_subject": _commit_subject(command.command_type, command.ecid),
                    "execution_capability_profile": capability_profile,
                    "repository_mutation_allowed": mutation_allowed,
                },
                expires_at=command.expires_at,
                lease_seconds=900,
                now=occurred_at,
            )
            self._stage(
                database,
                offer=offer,
                event_type=EventType.ENGINEERING_CONTROLLED_OFFER_CREATED,
                now=occurred_at,
            )
            created += 1
        return created

    async def acquire_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        session_id: UUID,
        offer_id: UUID,
        now: datetime,
    ) -> ControlledExecutionOffer:
        offer = await self.repository.get_offer_for_update(
            database,
            company_id=worker_context.company_id,
            offer_id=offer_id,
        )
        if offer is None:
            raise ControlledExecutionNotFoundError("Execution offer was not found.")
        if (
            offer.state != ControlledOfferState.AVAILABLE.value
            or offer.expires_at <= now
        ):
            raise ControlledExecutionIneligibleError("Execution offer is unavailable.")
        if (
            offer.command_type == ControlledCommandType.EXECUTE_CODE.value
            and "execution_capability_profile" in offer.payload
        ):
            readiness_source = await self.repository.acquisition_readiness(
                database,
                company_id=worker_context.company_id,
                command_id=offer.command_id,
            )
            if readiness_source is None:
                raise ControlledExecutionIneligibleError(
                    "Execution offer has no current scheduler repository identity."
                )
            milestone, roadmap = readiness_source
            from app.engineering_control.repository_readiness import (
                readiness_is_current,
            )

            if (
                roadmap.expected_head != offer.payload.get("expected_head")
                or not readiness_is_current(
                    dict(milestone.starting_commit_evidence),
                    repository_key=str(offer.payload.get("repository_key", "")),
                    branch=str(offer.payload.get("expected_branch", "")),
                    candidate_head=str(offer.payload.get("expected_head", "")),
                    worker_id=worker_context.worker_id,
                    now=now,
                )
            ):
                raise ControlledExecutionIneligibleError(
                    "Execution base is no longer current for this worker."
                )
        lease = await self.workers.acquire_lease_in_transaction(
            database,
            worker_context=worker_context,
            offer=ExecutionOffer(
                offer_id=offer.id,
                execution_id=offer.execution_id,
                correlation_id=offer.correlation_id,
                capability_required=WorkerCapability(offer.capability_required),
                lease_duration=timedelta(seconds=offer.lease_seconds),
                expires_at=offer.expires_at,
                metadata=immutable_mapping({}),
            ),
            now=now,
        )
        bound = await self.repository.bind_offer(
            database,
            offer=offer,
            lease_id=lease.id,
            worker_id=worker_context.worker_id,
            session_id=session_id,
            now=now,
        )
        execution = await database.get(EngineeringExecution, offer.execution_id)
        if execution is None:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            )
        execution.state = EngineeringExecutionState.RUNNING.value
        execution.status = EngineeringExecutionStatus.RUNNING.value
        execution.failure_classification = None
        execution.started_at = now
        execution.updated_at = now
        execution.version += 1
        self._stage(
            database,
            offer=bound,
            event_type=EventType.ENGINEERING_CONTROLLED_OFFER_ACQUIRED,
            now=now,
        )
        return bound

    async def complete_in_transaction(
        self,
        database: AsyncSession,
        *,
        worker_context: AuthenticatedWorkerContext,
        session_id: UUID,
        offer_id: UUID,
        lease_id: UUID,
        outcome: ControlledOutcome,
        output: dict[str, object],
        error_classification: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> ControlledExecutionResult:
        serialized = json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
        if len(serialized) > MAX_OUTPUT_BYTES:
            raise ControlledExecutionPayloadError("Controlled result is too large.")
        mutation = output.get("repository_mutated")
        if mutation not in {True, False}:
            raise ControlledExecutionPayloadError(
                "Controlled result must declare repository mutation truth."
            )
        if outcome is ControlledOutcome.SUCCEEDED:
            expected = {
                "workspace_id",
                "repository_key",
                "branch",
                "head",
                "clean",
                "file_count",
                "file_boundary",
                "repository_mutated",
            }
            if mutation is True:
                expected |= {
                    "starting_head",
                    "commit_sha",
                    "published_commit_sha",
                    "remote_head_before",
                    "mechanically_reconciled",
                    "validation",
                    "validation_runs",
                    "validation_environment",
                    "evidence",
                }
            elif "validation" in output:
                expected |= {
                    "validation",
                    "validation_runs",
                    "validation_environment",
                    "evidence",
                }
            boundary = output.get("file_boundary")
            if (
                set(output) != expected
                or output.get("clean") is not True
                or not isinstance(output.get("file_count"), int)
                or not isinstance(boundary, (list, tuple))
                or output.get("file_count") != len(boundary)
                or len(boundary) > 500
                or any(
                    not isinstance(item, str)
                    or len(item) > 500
                    or not _safe_relative_path(item)
                    for item in boundary
                )
                or list(boundary) != sorted(set(boundary))
            ):
                raise ControlledExecutionPayloadError(
                    "Successful controlled result shape is invalid."
                )
        elif not _valid_failed_output(output):
            raise ControlledExecutionPayloadError(
                "Failed controlled result diagnostics are invalid."
            )
        if (
            error_classification is not None
            and SAFE_ERROR.fullmatch(error_classification) is None
        ):
            raise ControlledExecutionPayloadError("Failure classification is invalid.")
        offer = await self.repository.get_offer_for_update(
            database,
            company_id=worker_context.company_id,
            offer_id=offer_id,
        )
        if offer is None:
            raise ControlledExecutionNotFoundError("Execution offer was not found.")
        existing_result = await database.scalar(
            select(ControlledExecutionResultModel).where(
                ControlledExecutionResultModel.company_id == worker_context.company_id,
                ControlledExecutionResultModel.offer_id == offer_id,
            )
        )
        if existing_result is not None:
            if (
                existing_result.lease_id == lease_id
                and existing_result.worker_id == worker_context.worker_id
                and existing_result.outcome == outcome.value
                and existing_result.output == output
                and existing_result.error_classification == error_classification
                and existing_result.started_at == started_at
                and existing_result.completed_at == completed_at
            ):
                return self.repository.result_record(existing_result)
            raise ControlledExecutionConflictError(
                "A conflicting terminal result already exists."
            )
        if (
            offer.state != ControlledOfferState.ACQUIRED.value
            or offer.worker_id != worker_context.worker_id
            or offer.lease_id != lease_id
        ):
            raise ControlledExecutionIneligibleError(
                "Execution result binding is invalid."
            )
        if offer.session_id != session_id:
            # A signed pending result may be redelivered after reconnect by the
            # same enrolled worker and original lease. Rebind only the session;
            # command, offer, lease, execution, and result identity are unchanged.
            offer.session_id = session_id
            offer.updated_at = completed_at
            offer.version += 1
        validation_output = output.get("validation")
        validation_runs_output = output.get("validation_runs")
        if outcome is not ControlledOutcome.SUCCEEDED and (
            output.get("workspace_id") != offer.workspace_id
            or output.get("repository_key") != offer.payload.get("repository_key")
            or output.get("branch") != offer.payload.get("expected_branch")
            or output.get("starting_head") != offer.payload.get("expected_head")
        ):
            raise ControlledExecutionPayloadError(
                "Failed controlled result does not match the immutable offer."
            )
        if outcome is ControlledOutcome.SUCCEEDED and (
            output.get("workspace_id") != offer.workspace_id
            or output.get("repository_key") != offer.payload.get("repository_key")
            or output.get("branch") != offer.payload.get("expected_branch")
            or (
                mutation is False
                and output.get("head") != offer.payload.get("expected_head")
            )
            or (
                mutation is False
                and offer.command_type == "execute_code"
                and (
                    offer.payload.get("execution_capability_profile")
                    != "inspect_validate_only"
                    or offer.payload.get("repository_mutation_allowed") is not False
                    or not isinstance(validation_output, dict)
                    or not validation_output
                    or not all(value is True for value in validation_output.values())
                    or not isinstance(validation_runs_output, list)
                    or not validation_runs_output
                    or len(validation_runs_output) > MAX_VALIDATION_RUNS
                    or not all(_valid_validation_run(run) for run in validation_runs_output)
                    or not isinstance(output.get("validation_environment"), dict)
                )
            )
            or (
                mutation is True
                and (
                    offer.command_type != "execute_code"
                    or output.get("starting_head") != offer.payload.get("expected_head")
                    or output.get("head") != output.get("commit_sha")
                    or output.get("head") != output.get("published_commit_sha")
                    or not re.fullmatch(r"[0-9a-f]{40}", str(output.get("commit_sha")))
                    or not re.fullmatch(
                        r"[0-9a-f]{40}", str(output.get("remote_head_before"))
                    )
                    or not isinstance(output.get("mechanically_reconciled"), bool)
                    or not isinstance(validation_output, dict)
                    or not all(value is True for value in validation_output.values())
                    or not isinstance(validation_runs_output, list)
                    or not validation_runs_output
                    or len(validation_runs_output) > MAX_VALIDATION_RUNS
                    or not all(
                        _valid_validation_run(run) for run in validation_runs_output
                    )
                    or not isinstance(output.get("validation_environment"), dict)
                )
            )
        ):
            raise ControlledExecutionPayloadError(
                "Controlled result does not match the immutable offer."
            )
        command = await database.get(EngineeringCommand, offer.command_id)
        lease = await database.get(WorkerLease, lease_id)
        if (
            command is None
            or command.company_id != worker_context.company_id
            or command.approval_state != EngineeringApprovalState.APPROVED.value
            or command.canceled_at is not None
            or command.expires_at <= completed_at
            or lease is None
            or lease.company_id != worker_context.company_id
            or lease.worker_id != worker_context.worker_id
            or lease.status != "active"
            or lease.expires_at <= completed_at
        ):
            raise ControlledExecutionIneligibleError(
                "Execution authority is no longer active."
            )
        if offer.expires_at <= completed_at:
            raise ControlledExecutionIneligibleError("Execution offer has expired.")
        if completed_at < started_at or started_at < (offer.acquired_at or started_at):
            raise ControlledExecutionPayloadError("Execution timestamps are invalid.")
        result = await self.repository.create_result(
            database,
            offer=offer,
            outcome=outcome,
            output=output,
            error_classification=error_classification,
            started_at=started_at,
            completed_at=completed_at,
            repository_mutated=bool(mutation),
        )
        if mutation is True:
            evidence = output.get("evidence")
            phases = evidence.get("phases", []) if isinstance(evidence, dict) else []
            expected_phases = [
                "composed",
                "workspace_ready",
                "executing",
                "validating",
                "commit_ready",
                "publishing_result",
                "completed",
            ]
            if phases != expected_phases:
                raise ControlledExecutionPayloadError(
                    "Provider lifecycle evidence is incomplete."
                )
            for sequence, phase in enumerate(phases, start=1):
                database.add(
                    ProviderExecutionTransition(
                        company_id=offer.company_id,
                        node_id=UUID(str(offer.payload["node_id"])),
                        command_id=offer.command_id,
                        execution_id=offer.execution_id,
                        lease_id=lease_id,
                        sequence=sequence,
                        phase=phase,
                        evidence=(
                            {
                                "commit_sha": output.get("commit_sha"),
                                "files": output.get("file_boundary"),
                            }
                            if phase == "completed"
                            else {}
                        ),
                        occurred_at=completed_at,
                    )
                )
        await self.workers.release_lease_in_transaction(
            database,
            worker_context=worker_context,
            lease_id=lease_id,
            now=completed_at,
        )
        execution = await database.get(EngineeringExecution, offer.execution_id)
        if execution is None:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            )
        succeeded = outcome is ControlledOutcome.SUCCEEDED
        execution.state = (
            EngineeringExecutionState.COMPLETED.value
            if succeeded
            else EngineeringExecutionState.FAILED.value
        )
        execution.status = (
            EngineeringExecutionStatus.SUCCEEDED.value
            if succeeded
            else EngineeringExecutionStatus.FAILED.value
        )
        execution.evidence_summary = dict(output)
        required_evidence = output.get("validation")
        run_evidence = output.get("validation_runs")
        execution.validation_summary = {
            "controlled_execution": True,
            "repository_mutated": bool(mutation),
            "required": dict(required_evidence)
            if isinstance(required_evidence, dict)
            else {},
            "runs": list(run_evidence) if isinstance(run_evidence, list) else [],
        }
        execution.failure_classification = error_classification
        execution.finished_at = completed_at
        execution.updated_at = completed_at
        execution.version += 1
        self._stage(
            database,
            offer=_offer_record(offer),
            event_type=(
                EventType.ENGINEERING_CONTROLLED_EXECUTION_COMPLETED
                if succeeded
                else EventType.ENGINEERING_CONTROLLED_EXECUTION_FAILED
            ),
            now=completed_at,
            result_id=result.id,
            repository_mutated=bool(mutation),
        )
        return result

    def _require(self, context: AuthorizationContext) -> None:
        try:
            self.authorization.require_permission(
                context, EngineeringExecutionPermission.REQUEST
            )
        except PermissionDeniedError as error:
            raise ControlledExecutionNotFoundError(
                "Engineering Execution was not found."
            ) from error

    def _stage(
        self,
        session: AsyncSession,
        *,
        offer: ControlledExecutionOffer,
        event_type: EventType,
        now: datetime,
        result_id: UUID | None = None,
        repository_mutated: bool = False,
    ) -> None:
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_controlled_execution",
                entity_id=result_id or offer.id,
                company_id=offer.company_id,
                payload={
                    "offer_id": str(offer.id),
                    "command_id": str(offer.command_id),
                    "execution_id": str(offer.execution_id),
                    "state": offer.state.value,
                    "capability": offer.capability_required.value,
                    "repository_mutated": repository_mutated,
                },
                correlation_id=offer.correlation_id,
                occurred_at=now,
            ),
        )


def _offer_record(entity) -> ControlledExecutionOffer:
    from .repository import _offer

    return _offer(entity)


def _safe_relative_path(value: str) -> bool:
    parts = value.split("/")
    return (
        bool(value)
        and not value.startswith("/")
        and all(part not in {"", ".", "..", ".git"} for part in parts)
    )


def _commit_subject(command_type: str, ecid: str) -> str:
    scope = "engineering" if command_type == "mission_control_milestone" else "devx"
    return f"feat({scope}): complete {ecid.lower()} controlled execution"
