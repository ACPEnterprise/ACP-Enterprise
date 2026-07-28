import hashlib
import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.operational_migration.cutover_models import (
    MigrationArtifact,
    MigrationArtifactAttempt,
    MigrationAuditSummary,
    MigrationCutoverAssessment,
    MigrationHistoryEntry,
    MigrationPhaseCompletion,
    MigrationRecordOutcome,
    utc_now,
)
from app.operational_migration.cutover_repository import (
    CutoverMigrationRepository,
)
from app.operational_migration.models import OperationalMigrationRun
from app.operational_migration.service import MigrationReport
from app.platform.permissions.authorization import AuthorizationContext

Disposition = Literal["accepted", "rejected", "duplicate", "unresolved"]
ParentType = Literal[
    "customer", "service_location", "job", "appointment", "estimate", "invoice"
]


class CutoverMigrationError(ValueError):
    pass


@dataclass(frozen=True)
class HistoryMigrationRecord:
    source_id: str
    parent_type: ParentType
    source_parent_id: str
    entry_type: Literal["note", "activity"]
    occurred_at: datetime
    summary_text: str
    activity_category: str
    employee_source_reference: str | None = None
    target_employee_id: UUID | None = None
    tags: tuple[str, ...] = ()
    attributes: dict[str, object] | None = None
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class ArtifactMigrationRecord:
    source_id: str
    parent_type: ParentType
    source_parent_id: str
    artifact_category: Literal["attachment", "document", "photo", "other"]
    original_filename: str | None
    media_type: str | None
    byte_size: int | None
    source_checksum: str | None
    transfer_outcome: Literal[
        "pending", "transferred", "retryable_failure", "nonretryable_failure"
    ]
    acp_checksum: str | None = None
    failure_classification: str | None = None
    required_for_cutover: bool = True
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class CutoverProgress:
    run_id: UUID
    processed: int
    source: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int


@dataclass(frozen=True)
class CutoverReadiness:
    assessment_id: UUID
    ready: bool
    projected_status: str
    blocker_codes: tuple[str, ...]
    facts: dict[str, object]


class CutoverMigrationService:
    """Migration-owned history, artifact, resume, and cutover orchestration."""

    supported_tags = frozenset({"priority", "vip", "warranty"})
    supported_attributes = frozenset({"legacy_category", "source_status"})

    def __init__(self, repository: CutoverMigrationRepository | None = None) -> None:
        self._repository = repository or CutoverMigrationRepository()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _source_system(value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or len(normalized) > 80:
            raise CutoverMigrationError("source_system must contain 1 to 80 characters")
        return normalized

    @staticmethod
    def _json(value: dict[str, object] | None, label: str) -> dict[str, object]:
        normalized = dict(value or {})
        try:
            json.dumps(normalized, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise CutoverMigrationError(
                f"{label} must be JSON serializable."
            ) from error
        return normalized

    @staticmethod
    def _event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        payload: dict[str, object],
    ) -> None:
        assert context.active_branch is not None
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                user_id=context.user.id,
                payload=payload,
            ),
        )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        history: Sequence[HistoryMigrationRecord],
        artifacts: Sequence[ArtifactMigrationRecord],
        dry_run: bool,
        resume_run_id: UUID | None = None,
        interrupt_after: int | None = None,
        progress_callback: Callable[[CutoverProgress], None] | None = None,
    ) -> MigrationReport:
        source_system = self._source_system(source_system)
        if context.active_branch is None or not context.can_access_branch(
            context.active_branch.id
        ):
            raise CutoverMigrationError("An authorized active Branch is required.")
        digest = hashlib.sha256(
            json.dumps(
                {
                    "source_system": source_system,
                    "history": [asdict(record) for record in history],
                    "artifacts": [asdict(record) for record in artifacts],
                },
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        if resume_run_id is None:
            async with factory() as session, session.begin():
                run = OperationalMigrationRun(
                    company_id=context.company.id,
                    branch_id=context.active_branch.id,
                    initiated_by_user_id=context.user.id,
                    source_system=source_system,
                    source_digest=digest,
                    mode="dry_run" if dry_run else "import",
                    status="running",
                )
                session.add(run)
                await session.flush()
                run_id = run.id
        else:
            if dry_run:
                raise CutoverMigrationError("Dry runs cannot resume import runs.")
            async with factory() as session, session.begin():
                existing_run = await self._repository.get_run_for_update(
                    session, resume_run_id
                )
                if (
                    existing_run is None
                    or existing_run.company_id != context.company.id
                    or existing_run.branch_id != context.active_branch.id
                    or existing_run.status != "interrupted"
                    or existing_run.source_digest != digest
                ):
                    raise CutoverMigrationError(
                        "Run is not an interrupted matching migration."
                    )
                existing_run.status = "running"
                existing_run.completed_at = None
                run_id = existing_run.id

        records: list[tuple[str, HistoryMigrationRecord | ArtifactMigrationRecord]] = [
            *(
                ("note" if item.entry_type == "note" else "activity", item)
                for item in history
            ),
            *(("artifact", item) for item in artifacts),
        ]
        local: Counter[str] = Counter()
        processed_this_attempt = 0
        try:
            if dry_run:
                async with factory() as session:
                    transaction = await session.begin()
                    for entity_type, record in records:
                        result = await self._process(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            entity_type=entity_type,
                            record=record,
                            persist_outcome=False,
                        )
                        local[result] += 1
                        processed_this_attempt += 1
                        self._progress(
                            progress_callback,
                            run_id,
                            processed_this_attempt,
                            len(records),
                            local,
                        )
                    await transaction.rollback()
            else:
                for entity_type, record in records:
                    source_hash = self._hash(record.source_id)
                    async with factory() as session:
                        previous = await self._repository.outcome(
                            session,
                            run_id=run_id,
                            entity_type=entity_type,
                            source_hash=source_hash,
                        )
                    if previous is not None and (
                        previous.disposition in {"accepted", "duplicate", "unresolved"}
                        or not previous.retry_eligible
                    ):
                        continue
                    async with factory() as session, session.begin():
                        result = await self._process(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            entity_type=entity_type,
                            record=record,
                            persist_outcome=True,
                            previous=previous,
                        )
                    local[result] += 1
                    processed_this_attempt += 1
                    self._progress(
                        progress_callback,
                        run_id,
                        processed_this_attempt,
                        len(records),
                        local,
                    )
                    if (
                        interrupt_after is not None
                        and processed_this_attempt >= interrupt_after
                    ):
                        return await self._finalize(
                            factory, run_id=run_id, status="interrupted"
                        )
        except Exception:
            await self._finalize(factory, run_id=run_id, status="failed")
            raise
        return await self._finalize(
            factory,
            run_id=run_id,
            status=(
                "completed_with_exceptions"
                if local["rejected"] or local["unresolved"]
                else "completed"
            ),
            dry_run_counts=local if dry_run else None,
        )

    async def _process(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        entity_type: str,
        record: HistoryMigrationRecord | ArtifactMigrationRecord,
        persist_outcome: bool,
        previous: MigrationRecordOutcome | None = None,
    ) -> Disposition:
        source_hash = self._hash(record.source_id)
        disposition: Disposition = "accepted"
        reason: str | None = None
        linked = False
        try:
            self._validate_identity(record.source_id)
            parent_id = await self._repository.get_parent_identity(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,  # type: ignore[union-attr]
                source_system=source_system,
                parent_type=record.parent_type,
                source_parent_id=record.source_parent_id,
            )
            if parent_id is None:
                disposition, reason = "unresolved", "missing_or_wrong_scope_parent"
            elif isinstance(record, HistoryMigrationRecord):
                linked = True
                disposition, reason = await self._history(
                    session,
                    context=context,
                    run_id=run_id,
                    source_system=source_system,
                    source_hash=source_hash,
                    parent_id=parent_id,
                    record=record,
                )
            else:
                linked = True
                disposition, reason = await self._artifact(
                    session,
                    context=context,
                    run_id=run_id,
                    source_system=source_system,
                    source_hash=source_hash,
                    parent_id=parent_id,
                    record=record,
                )
        except CutoverMigrationError as error:
            disposition, reason = "rejected", str(error)
        if persist_outcome:
            retry_eligible = reason == "artifact_transfer_retryable"
            if previous is None:
                self._repository.add_outcome(
                    session,
                    MigrationRecordOutcome(
                        run_id=run_id,
                        entity_type=entity_type,
                        source_id_sha256=source_hash,
                        disposition=disposition,
                        reason_code=reason,
                        retry_eligible=retry_eligible,
                        attempt_count=1,
                        parent_linked=linked,
                    ),
                )
            else:
                previous.disposition = disposition
                previous.reason_code = reason
                previous.retry_eligible = retry_eligible
                previous.attempt_count += 1
                previous.parent_linked = linked
        return disposition

    @staticmethod
    def _validate_identity(value: str) -> None:
        if not value.strip() or len(value) > 191:
            raise CutoverMigrationError("source_identifier_invalid")

    async def _history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        source_hash: str,
        parent_id: UUID,
        record: HistoryMigrationRecord,
    ) -> tuple[Disposition, str | None]:
        if await self._repository.history_exists(
            session,
            company_id=context.company.id,
            source_system=source_system,
            source_hash=source_hash,
        ):
            return "duplicate", "source_identity_exists"
        text = " ".join(record.summary_text.split())
        if not text or len(text) > 4000:
            raise CutoverMigrationError("history_summary_invalid")
        category = record.activity_category.strip().lower()
        if not category or len(category) > 64:
            raise CutoverMigrationError("activity_category_invalid")
        employee_hash = (
            self._hash(record.employee_source_reference)
            if record.employee_source_reference
            else None
        )
        if record.target_employee_id is not None:
            if not await self._repository.employee_is_authoritative(
                session,
                company_id=context.company.id,
                employee_id=record.target_employee_id,
            ):
                raise CutoverMigrationError("employee_wrong_company")
            attribution_status = "resolved"
        elif employee_hash:
            attribution_status = "unresolved"
        else:
            attribution_status = "not_provided"
        supported_tags = sorted(
            {tag.strip().lower() for tag in record.tags} & self.supported_tags
        )
        unsupported_tags = sorted(
            {tag.strip().lower() for tag in record.tags} - self.supported_tags
        )
        attributes = self._json(record.attributes, "attributes")
        normalized_attributes = {
            key: value
            for key, value in attributes.items()
            if key in self.supported_attributes
        }
        unsupported_keys = sorted(
            (attributes.keys() - self.supported_attributes)
            | {f"tag:{tag}" for tag in unsupported_tags}
        )
        entry = MigrationHistoryEntry(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=context.active_branch.id,  # type: ignore[union-attr]
            source_system=source_system,
            source_id_sha256=source_hash,
            parent_type=record.parent_type,
            parent_id=parent_id,
            entry_type=record.entry_type,
            occurred_at=record.occurred_at,
            employee_source_ref_sha256=employee_hash,
            employee_id=record.target_employee_id,
            attribution_status=attribution_status,
            summary_text=text,
            activity_category=category,
            supported_tags=supported_tags,
            normalized_attributes=normalized_attributes,
            unsupported_attribute_keys=unsupported_keys,
            external_metadata=self._json(record.external_metadata, "metadata"),
            first_run_id=run_id,
        )
        self._repository.add_history(session, entry)
        self._event(
            session,
            context=context,
            event_type=(
                EventType.NOTE_MIGRATED
                if record.entry_type == "note"
                else EventType.ACTIVITY_MIGRATED
            ),
            entity_type=record.entry_type,
            entity_id=entry.id,
            payload={
                "parent_type": record.parent_type,
                "parent_id": str(parent_id),
                "attribution_status": attribution_status,
                "origin": "migration",
            },
        )
        return "accepted", (
            "unresolved_employee_reference"
            if attribution_status == "unresolved"
            else None
        )

    async def _artifact(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        source_hash: str,
        parent_id: UUID,
        record: ArtifactMigrationRecord,
    ) -> tuple[Disposition, str | None]:
        if await self._repository.artifact_by_source(
            session,
            company_id=context.company.id,
            source_system=source_system,
            source_hash=source_hash,
        ):
            return "duplicate", "source_identity_exists"
        if record.source_checksum and await self._repository.artifact_by_checksum(
            session,
            company_id=context.company.id,
            source_checksum=record.source_checksum,
        ):
            return "duplicate", "artifact_checksum_exists"
        if record.byte_size is not None and record.byte_size < 0:
            raise CutoverMigrationError("artifact_size_invalid")
        if record.original_filename and (
            "/" in record.original_filename or "\\" in record.original_filename
        ):
            raise CutoverMigrationError("artifact_filename_invalid")
        state = {
            "pending": ("available", "pending", "pending", False, None),
            "transferred": ("available", "transferred", "valid", False, None),
            "retryable_failure": (
                "available",
                "failed",
                "not_validated",
                True,
                record.failure_classification or "transfer_transient",
            ),
            "nonretryable_failure": (
                "unavailable",
                "failed",
                "not_validated",
                False,
                record.failure_classification or "source_unavailable",
            ),
        }[record.transfer_outcome]
        retrieval, transfer, validation, retryable, failure = state
        artifact = MigrationArtifact(
            id=uuid4(),
            company_id=context.company.id,
            branch_id=context.active_branch.id,  # type: ignore[union-attr]
            source_system=source_system,
            source_id_sha256=source_hash,
            parent_type=record.parent_type,
            parent_id=parent_id,
            artifact_category=record.artifact_category,
            original_filename=record.original_filename,
            media_type=record.media_type,
            byte_size=record.byte_size,
            source_checksum=record.source_checksum,
            acp_checksum=record.acp_checksum,
            retrieval_state=retrieval,
            transfer_state=transfer,
            validation_state=validation,
            failure_classification=failure,
            retry_eligible=retryable,
            required_for_cutover=record.required_for_cutover,
            attempt_count=1,
            imported_at=utc_now() if transfer == "transferred" else None,
            external_metadata=self._json(record.external_metadata, "metadata"),
            first_run_id=run_id,
        )
        attempt = MigrationArtifactAttempt(
            artifact_id=artifact.id,
            run_id=run_id,
            attempt_number=1,
            outcome=record.transfer_outcome,
            failure_classification=failure,
            retry_eligible=retryable,
        )
        await self._repository.add_artifact(session, artifact, attempt)
        self._event(
            session,
            context=context,
            event_type=(
                EventType.ARTIFACT_MIGRATED
                if transfer == "transferred"
                else EventType.ARTIFACT_REGISTERED
            ),
            entity_type="migration_artifact",
            entity_id=artifact.id,
            payload={
                "parent_type": record.parent_type,
                "parent_id": str(parent_id),
                "transfer_state": transfer,
                "origin": "migration",
            },
        )
        return "accepted", (
            "artifact_transfer_retryable"
            if retryable
            else "artifact_transfer_nonretryable"
            if transfer == "failed"
            else None
        )

    async def retry_artifact(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        source_id: str,
        acp_checksum: str,
    ) -> MigrationArtifact:
        source_hash = self._hash(source_id)
        async with factory() as session, session.begin():
            artifact = await self._repository.artifact_by_source(
                session,
                company_id=context.company.id,
                source_system=self._source_system(source_system),
                source_hash=source_hash,
            )
            if (
                artifact is None or artifact.branch_id != context.active_branch.id  # type: ignore[union-attr]
            ):
                raise CutoverMigrationError("Artifact was not found.")
            if not artifact.retry_eligible or artifact.transfer_state != "failed":
                raise CutoverMigrationError("Artifact failure is not retryable.")
            artifact.transfer_state = "transferred"
            artifact.validation_state = "valid"
            artifact.acp_checksum = acp_checksum
            artifact.retry_eligible = False
            artifact.failure_classification = None
            artifact.attempt_count += 1
            artifact.imported_at = utc_now()
            artifact.updated_at = utc_now()
            session.add(
                MigrationArtifactAttempt(
                    artifact_id=artifact.id,
                    run_id=artifact.first_run_id,
                    attempt_number=artifact.attempt_count,
                    outcome="transferred",
                    retry_eligible=False,
                )
            )
            self._event(
                session,
                context=context,
                event_type=EventType.ARTIFACT_MIGRATED,
                entity_type="migration_artifact",
                entity_id=artifact.id,
                payload={"transfer_state": "transferred", "origin": "migration_retry"},
            )
        return artifact

    async def record_phase_completion(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        phase_code: str,
        supporting_run_id: UUID,
        required: bool = True,
        dry_run_completed: bool,
        import_completed: bool,
        idempotent_rerun_validated: bool,
    ) -> None:
        async with factory() as session, session.begin():
            run = await session.get(OperationalMigrationRun, supporting_run_id)
            if (
                run is None
                or run.company_id != context.company.id
                or run.branch_id != context.active_branch.id  # type: ignore[union-attr]
                or run.status not in {"completed", "completed_with_exceptions"}
            ):
                raise CutoverMigrationError(
                    "Phase completion requires a completed tenant-owned run."
                )
            await self._repository.upsert_phase_completion(
                session,
                MigrationPhaseCompletion(
                    company_id=context.company.id,
                    branch_id=context.active_branch.id,  # type: ignore[union-attr]
                    phase_code=phase_code,
                    required=required,
                    dry_run_completed=dry_run_completed,
                    import_completed=import_completed,
                    idempotent_rerun_validated=idempotent_rerun_validated,
                    supporting_run_id=supporting_run_id,
                ),
            )

    async def assess_readiness(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        required_phases: Sequence[str],
    ) -> CutoverReadiness:
        assert context.active_branch is not None
        async with factory() as session, session.begin():
            runs = await self._repository.runs_for_scope(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            run_ids = [run.id for run in runs]
            outcomes = [
                outcome
                for run_id in run_ids
                for outcome in await self._repository.outcomes_for_run(session, run_id)
            ]
            artifacts = await self._repository.artifacts_for_scope(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            phases = await self._repository.phase_completions(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            phase_map = {phase.phase_code: phase for phase in phases}
            unresolved_employees = await self._repository.unresolved_attributions(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            blockers: set[str] = set()
            if any(run.status in {"running", "interrupted", "failed"} for run in runs):
                blockers.add("incomplete_runs")
            if any(outcome.disposition == "unresolved" for outcome in outcomes):
                blockers.add("unresolved_parents")
            if any(
                outcome.disposition == "rejected" and outcome.retry_eligible
                for outcome in outcomes
            ):
                blockers.add("retryable_failures")
            if any(
                outcome.disposition == "rejected" and not outcome.retry_eligible
                for outcome in outcomes
            ):
                blockers.add("owner_disposition_required")
            if unresolved_employees:
                blockers.add("unresolved_employee_references")
            required_artifact_failures = sum(
                artifact.required_for_cutover
                and (
                    artifact.transfer_state != "transferred"
                    or artifact.validation_state != "valid"
                )
                for artifact in artifacts
            )
            if required_artifact_failures:
                blockers.add("required_artifacts_incomplete")
            incomplete_phases = [
                phase_code
                for phase_code in required_phases
                if phase_code not in phase_map
                or not phase_map[phase_code].dry_run_completed
                or not phase_map[phase_code].import_completed
                or not phase_map[phase_code].idempotent_rerun_validated
            ]
            if incomplete_phases:
                blockers.add("required_phases_incomplete")
            disposition_counts = Counter(outcome.disposition for outcome in outcomes)
            entity_counts = Counter(outcome.entity_type for outcome in outcomes)
            entity_reconciliation = {
                entity_type: dict(
                    Counter(
                        outcome.disposition
                        for outcome in outcomes
                        if outcome.entity_type == entity_type
                    )
                )
                for entity_type in sorted(entity_counts)
            }
            facts: dict[str, object] = {
                "source_records": len(outcomes),
                "accepted": disposition_counts["accepted"],
                "rejected": disposition_counts["rejected"],
                "duplicate": disposition_counts["duplicate"],
                "unresolved": disposition_counts["unresolved"],
                "linked": sum(outcome.parent_linked for outcome in outcomes),
                "unlinked": sum(not outcome.parent_linked for outcome in outcomes),
                "skipped": disposition_counts["skipped"],
                "retried": sum(
                    max(outcome.attempt_count - 1, 0) for outcome in outcomes
                )
                + sum(max(artifact.attempt_count - 1, 0) for artifact in artifacts),
                "imported": disposition_counts["accepted"],
                "records_by_entity_type": dict(entity_counts),
                "entity_reconciliation": entity_reconciliation,
                "unresolved_employee_references": unresolved_employees,
                "required_artifacts_incomplete": required_artifact_failures,
                "failed_records_retry_eligible": sum(
                    outcome.disposition == "rejected" and outcome.retry_eligible
                    for outcome in outcomes
                )
                + sum(
                    artifact.transfer_state == "failed" and artifact.retry_eligible
                    for artifact in artifacts
                ),
                "failed_records_owner_disposition": sum(
                    outcome.disposition == "rejected" and not outcome.retry_eligible
                    for outcome in outcomes
                )
                + sum(
                    artifact.transfer_state == "failed" and not artifact.retry_eligible
                    for artifact in artifacts
                ),
                "open_migration_exceptions": await self._repository.count_open_exceptions(
                    session, run_ids=run_ids
                ),
                "completed_phases": sorted(phase_map),
                "incomplete_required_phases": sorted(incomplete_phases),
                "dry_run_completion_recorded": not incomplete_phases
                and all(
                    phase_map[phase].dry_run_completed for phase in required_phases
                ),
                "import_completion_recorded": not incomplete_phases
                and all(phase_map[phase].import_completed for phase in required_phases),
                "idempotent_rerun_validation_recorded": not incomplete_phases
                and all(
                    phase_map[phase].idempotent_rerun_validated
                    for phase in required_phases
                ),
                "reconciliation_difference": 0,
            }
            ready = not blockers
            assessment = MigrationCutoverAssessment(
                id=uuid4(),
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                evaluated_by_user_id=context.user.id,
                projected_status=("ready_for_owner_review" if ready else "not_ready"),
                ready=ready,
                blocker_codes=sorted(blockers),
                facts=facts,
            )
            self._repository.add_assessment(session, assessment)
            self._event(
                session,
                context=context,
                event_type=EventType.MIGRATION_CUTOVER_READINESS_EVALUATED,
                entity_type="migration_cutover_assessment",
                entity_id=assessment.id,
                payload={
                    "ready": ready,
                    "blocker_codes": sorted(blockers),
                    "schema_version": 1,
                },
            )
        return CutoverReadiness(
            assessment_id=assessment.id,
            ready=ready,
            projected_status=assessment.projected_status,
            blocker_codes=tuple(sorted(blockers)),
            facts=facts,
        )

    async def complete(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        readiness: CutoverReadiness,
        source_descriptor: str,
    ) -> MigrationAuditSummary:
        assert context.active_branch is not None
        async with factory() as session, session.begin():
            assessment = await session.get(
                MigrationCutoverAssessment, readiness.assessment_id
            )
            if (
                assessment is None
                or assessment.company_id != context.company.id
                or assessment.branch_id != context.active_branch.id
            ):
                raise CutoverMigrationError("Readiness assessment was not found.")
            runs = await self._repository.runs_for_scope(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            incomplete = any(
                run.status in {"running", "interrupted", "failed"} for run in runs
            )
            status = (
                "incomplete"
                if incomplete
                else "completed"
                if assessment.ready
                else "completed_with_exceptions"
            )
            artifacts = await self._repository.artifacts_for_scope(
                session,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
            )
            summary = MigrationAuditSummary(
                id=uuid4(),
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                assessment_id=assessment.id,
                source_descriptor_sha256=self._hash(source_descriptor),
                completion_status=status,
                entity_counts=dict(assessment.facts),
                artifact_outcomes=dict(
                    Counter(artifact.transfer_state for artifact in artifacts)
                ),
                reconciliation_differences={
                    "source_to_target": assessment.facts.get(
                        "reconciliation_difference", 0
                    ),
                    "parent_resolution": assessment.facts.get("unlinked", 0),
                    "financial_total": "not_measured",
                },
                unresolved_categories=list(assessment.blocker_codes),
                run_ids=[str(run.id) for run in runs],
                period_started_at=min((run.started_at for run in runs), default=None),
            )
            self._repository.add_summary(session, summary)
            if status != "incomplete":
                self._event(
                    session,
                    context=context,
                    event_type=(
                        EventType.MIGRATION_COMPLETED
                        if status == "completed"
                        else EventType.MIGRATION_COMPLETED_WITH_EXCEPTIONS
                    ),
                    entity_type="migration_audit_summary",
                    entity_id=summary.id,
                    payload={"completion_status": status, "schema_version": 1},
                )
        return summary

    async def _finalize(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        run_id: UUID,
        status: str,
        dry_run_counts: Counter[str] | None = None,
    ) -> MigrationReport:
        async with factory() as session, session.begin():
            run = await self._repository.get_run_for_update(session, run_id)
            if run is None:
                raise RuntimeError("Migration run disappeared.")
            if dry_run_counts is None:
                outcomes = await self._repository.outcomes_for_run(session, run_id)
                counts = Counter(outcome.disposition for outcome in outcomes)
            else:
                counts = dry_run_counts
            run.source_count = sum(counts.values())
            run.accepted_count = counts["accepted"]
            run.rejected_count = counts["rejected"]
            run.duplicate_count = counts["duplicate"]
            run.unresolved_count = counts["unresolved"]
            run.status = status
            run.completed_at = utc_now()
        return MigrationReport(
            run_id=run_id,
            mode=run.mode,
            source=run.source_count,
            accepted=run.accepted_count,
            rejected=run.rejected_count,
            duplicate=run.duplicate_count,
            unresolved=run.unresolved_count,
        )

    @staticmethod
    def _progress(
        callback: Callable[[CutoverProgress], None] | None,
        run_id: UUID,
        processed: int,
        source: int,
        counts: Counter[str],
    ) -> None:
        if callback:
            callback(
                CutoverProgress(
                    run_id=run_id,
                    processed=processed,
                    source=source,
                    accepted=counts["accepted"],
                    rejected=counts["rejected"],
                    duplicate=counts["duplicate"],
                    unresolved=counts["unresolved"],
                )
            )
