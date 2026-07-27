import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.engineering_control.repository_authorization.contracts import (
    RepositoryOperationType as AuthorizationOperationType,
)
from app.engineering_control.repository_authorization.errors import (
    RepositoryAuthorizationError,
    RepositoryAuthorizationNotFoundError,
)
from app.engineering_control.repository_authorization.records import (
    ValidateRepositoryAuthorization,
)
from app.engineering_control.repository_authorization.service import (
    EngineeringRepositoryAuthorizationService,
    engineering_repository_authorization_service,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    PermissionDeniedError,
    authorization_service,
)
from app.platform.permissions.codes import (
    EngineeringRepositoryOperationPermission,
)

from .contracts import (
    BoundedGitAdapter,
    RepositoryOperationEventType,
    RepositoryOperationReadiness,
    RepositoryOperationState,
    RepositoryOperationType,
)
from .errors import (
    RepositoryOperationConflictError,
    RepositoryOperationGitError,
    RepositoryOperationNotFoundError,
    RepositoryOperationPermissionError,
    RepositoryOperationReconciliationRequiredError,
    RepositoryOperationStateError,
    RepositoryOperationValidationError,
)
from .git_adapter import ProductionBoundedGitAdapter
from .records import ExecuteRepositoryCommit, RepositoryOperationRecord
from .repository import EngineeringRepositoryOperationRepository

IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
MAX_SUBJECT_LENGTH = 120
MAX_FAILURE_DETAIL = 240


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringRepositoryOperationService:
    def __init__(
        self,
        *,
        adapter: BoundedGitAdapter | None = None,
        repository: type[EngineeringRepositoryOperationRepository] = (
            EngineeringRepositoryOperationRepository
        ),
        authorizations: EngineeringRepositoryAuthorizationService = (
            engineering_repository_authorization_service
        ),
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.adapter = adapter
        self.repository = repository
        self.authorizations = authorizations
        self.authorization = authorization
        self.audit = audit
        self.events = events

    async def execute(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ExecuteRepositoryCommit,
        now: datetime | None = None,
    ) -> RepositoryOperationRecord:
        self._require(context, EngineeringRepositoryOperationPermission.EXECUTE)
        occurred_at = now or utc_now()
        subject = self._subject(command.commit_subject)
        self._idempotency(command.idempotency_key)
        adapter = self._adapter()
        try:
            operation = await self._reserve(
                session,
                context=context,
                command=command,
                subject=subject,
                now=occurred_at,
            )
        except RepositoryAuthorizationNotFoundError as error:
            raise RepositoryOperationNotFoundError(
                "Repository authorization not found."
            ) from error
        except RepositoryAuthorizationError as error:
            raise RepositoryOperationValidationError(
                "Repository authorization is not eligible."
            ) from error
        except IntegrityError as error:
            await session.rollback()
            raise RepositoryOperationConflictError(
                "Repository operation reservation conflicted."
            ) from error
        if operation.state is RepositoryOperationState.SUCCEEDED:
            return operation
        if operation.state is RepositoryOperationState.RECONCILIATION_REQUIRED:
            return await self.reconcile(
                session,
                context=context,
                command=command,
                operation_id=operation.id,
                now=occurred_at,
            )
        if operation.state is not RepositoryOperationState.RESERVED:
            raise RepositoryOperationConflictError(
                "Repository operation is already in progress or terminal."
            )

        try:
            self._validate_preflight(adapter, operation)
        except RepositoryOperationGitError as error:
            await self._finalize_failure(
                session,
                context=context,
                operation=operation,
                error=error,
                reconciliation=False,
                now=occurred_at,
            )
            raise

        operation = await self._start(
            session,
            context=context,
            operation=operation,
            now=occurred_at,
        )
        commit_sha: str | None = None
        try:
            adapter.stage_exact_files(operation.file_boundary)
            self._validate_staged(adapter, operation)
            commit_sha = adapter.create_commit(operation.commit_subject)
            self._validate_post_commit(adapter, operation, commit_sha)
        except RepositoryOperationGitError as error:
            await self._finalize_failure(
                session,
                context=context,
                operation=operation,
                error=error,
                reconciliation=True,
                resulting_commit_sha=commit_sha,
                now=utc_now(),
            )
            raise RepositoryOperationReconciliationRequiredError(
                "Repository operation requires reconciliation."
            ) from error

        try:
            return await self._finalize_success(
                session,
                context=context,
                operation=operation,
                command=command,
                commit_sha=commit_sha,
                now=utc_now(),
            )
        except Exception as error:
            await session.rollback()
            await self._mark_reconciliation_after_commit(
                session,
                context=context,
                operation=operation,
                commit_sha=commit_sha,
                now=utc_now(),
            )
            raise RepositoryOperationReconciliationRequiredError(
                "Commit exists but durable finalization requires reconciliation."
            ) from error

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ExecuteRepositoryCommit,
        operation_id: UUID,
        now: datetime | None = None,
    ) -> RepositoryOperationRecord:
        self._require(context, EngineeringRepositoryOperationPermission.EXECUTE)
        occurred_at = now or utc_now()
        adapter = self._adapter()
        async with session.begin():
            operation = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                operation_id=operation_id,
            )
            if operation is None:
                raise RepositoryOperationNotFoundError(
                    "Repository operation not found."
                )
            self._match_request(operation, command)
            if operation.state is RepositoryOperationState.SUCCEEDED:
                return operation
            if operation.state is not RepositoryOperationState.RECONCILIATION_REQUIRED:
                raise RepositoryOperationStateError(
                    "Repository operation is not reconcilable."
                )
        head = adapter.inspect_current_head()
        commit = adapter.inspect_commit(head)
        self._validate_commit(operation, commit)
        state = adapter.inspect_repository_state()
        if state.changed_files or state.staged_files:
            raise RepositoryOperationReconciliationRequiredError(
                "Repository remains dirty during reconciliation."
            )
        return await self._finalize_success(
            session,
            context=context,
            operation=operation,
            command=command,
            commit_sha=head,
            now=occurred_at,
            allowed_from=(RepositoryOperationState.RECONCILIATION_REQUIRED,),
        )

    async def readiness(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ExecuteRepositoryCommit,
        now: datetime | None = None,
    ) -> RepositoryOperationReadiness:
        self._require(context, EngineeringRepositoryOperationPermission.READ)
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                authorization_source = (
                    await self.repository.get_authorization_for_update(
                        session,
                        company_id=context.company.id,
                        authorization_id=command.authorization_id,
                    )
                )
                if authorization_source is None:
                    raise RepositoryOperationNotFoundError(
                        "Repository authorization not found."
                    )
                authorization = await self.authorizations.validate_in_transaction(
                    session,
                    context=context,
                    command=self._authorization_command(command, authorization_source),
                    now=occurred_at,
                )
            operation = self._synthetic_operation(authorization, command, occurred_at)
            self._validate_preflight(self._adapter(), operation)
        except (
            RepositoryAuthorizationError,
            RepositoryOperationGitError,
            RepositoryOperationValidationError,
        ) as error:
            return RepositoryOperationReadiness(
                False, type(error).__name__, occurred_at
            )
        return RepositoryOperationReadiness(True, None, occurred_at)

    async def get(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation_id: UUID,
    ) -> RepositoryOperationRecord:
        self._require(context, EngineeringRepositoryOperationPermission.READ)
        record = await self.repository.get_for_update(
            session,
            company_id=context.company.id,
            operation_id=operation_id,
        )
        if record is None:
            raise RepositoryOperationNotFoundError("Repository operation not found.")
        return record

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        limit: int = 50,
    ) -> tuple[RepositoryOperationRecord, ...]:
        self._require(context, EngineeringRepositoryOperationPermission.READ)
        if not 1 <= limit <= 100:
            raise RepositoryOperationValidationError("Limit is invalid.")
        return await self.repository.list(
            session, company_id=context.company.id, limit=limit
        )

    async def _reserve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ExecuteRepositoryCommit,
        subject: str,
        now: datetime,
    ) -> RepositoryOperationRecord:
        async with session.begin():
            existing = await self.repository.get_by_idempotency(
                session,
                company_id=context.company.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is not None:
                self._match_request(existing, command, subject=subject)
                return existing
            authorization_source = await self.repository.get_authorization_for_update(
                session,
                company_id=context.company.id,
                authorization_id=command.authorization_id,
            )
            if authorization_source is None:
                raise RepositoryOperationNotFoundError(
                    "Repository authorization not found."
                )
            authorization = await self.authorizations.validate_in_transaction(
                session,
                context=context,
                command=self._authorization_command(command, authorization_source),
                now=now,
            )
            existing = await self.repository.get_by_authorization(
                session,
                company_id=context.company.id,
                authorization_id=authorization.id,
            )
            if existing is not None:
                self._match_request(existing, command, subject=subject)
                return existing
            operation = await self.repository.create_reserved(
                session,
                authorization=authorization,
                requested_by_user_id=context.user.id,
                commit_subject=subject,
                boundary_digest=self._boundary_digest(authorization.file_boundary),
                idempotency_key=command.idempotency_key,
                now=now,
            )
            await self._event(
                session,
                context=context,
                operation=operation,
                history=RepositoryOperationEventType.REQUESTED,
                business=EventType.ENGINEERING_REPOSITORY_OPERATION_REQUESTED,
                now=now,
            )
            await self._event(
                session,
                context=context,
                operation=operation,
                history=RepositoryOperationEventType.RESERVED,
                business=EventType.ENGINEERING_REPOSITORY_OPERATION_RESERVED,
                now=now,
            )
            return operation

    async def _start(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation: RepositoryOperationRecord,
        now: datetime,
    ) -> RepositoryOperationRecord:
        async with session.begin():
            started = await self.repository.transition(
                session,
                company_id=context.company.id,
                operation_id=operation.id,
                expected_version=operation.version,
                from_states=(RepositoryOperationState.RESERVED,),
                target=RepositoryOperationState.EXECUTING,
                now=now,
            )
            if started is None:
                raise RepositoryOperationConflictError(
                    "Repository operation reservation changed."
                )
            await self._event(
                session,
                context=context,
                operation=started,
                history=RepositoryOperationEventType.STARTED,
                business=EventType.ENGINEERING_REPOSITORY_OPERATION_STARTED,
                now=now,
            )
            return started

    async def _finalize_success(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation: RepositoryOperationRecord,
        command: ExecuteRepositoryCommit,
        commit_sha: str,
        now: datetime,
        allowed_from: tuple[RepositoryOperationState, ...] = (
            RepositoryOperationState.EXECUTING,
        ),
    ) -> RepositoryOperationRecord:
        async with session.begin():
            current = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                operation_id=operation.id,
            )
            if current is None:
                raise RepositoryOperationNotFoundError(
                    "Repository operation not found."
                )
            if current.state is RepositoryOperationState.SUCCEEDED:
                return current
            if current.state not in allowed_from:
                raise RepositoryOperationStateError(
                    "Repository operation cannot be finalized."
                )
            await self.authorizations.consume_in_transaction(
                session,
                context=context,
                command=self._authorization_command(command, current),
                now=now,
            )
            succeeded = await self.repository.transition(
                session,
                company_id=context.company.id,
                operation_id=current.id,
                expected_version=current.version,
                from_states=allowed_from,
                target=RepositoryOperationState.SUCCEEDED,
                resulting_commit_sha=commit_sha,
                now=now,
            )
            if succeeded is None:
                raise RepositoryOperationConflictError(
                    "Repository operation finalization conflicted."
                )
            await self._event(
                session,
                context=context,
                operation=succeeded,
                history=RepositoryOperationEventType.SUCCEEDED,
                business=EventType.ENGINEERING_REPOSITORY_OPERATION_SUCCEEDED,
                now=now,
            )
            return succeeded

    async def _finalize_failure(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation: RepositoryOperationRecord,
        error: RepositoryOperationGitError,
        reconciliation: bool,
        now: datetime,
        resulting_commit_sha: str | None = None,
    ) -> RepositoryOperationRecord:
        target = (
            RepositoryOperationState.RECONCILIATION_REQUIRED
            if reconciliation
            else RepositoryOperationState.FAILED
        )
        async with session.begin():
            current = await self.repository.get_for_update(
                session,
                company_id=context.company.id,
                operation_id=operation.id,
            )
            if current is None:
                raise RepositoryOperationNotFoundError(
                    "Repository operation not found."
                )
            failed = await self.repository.transition(
                session,
                company_id=context.company.id,
                operation_id=current.id,
                expected_version=current.version,
                from_states=(
                    RepositoryOperationState.RESERVED,
                    RepositoryOperationState.EXECUTING,
                ),
                target=target,
                resulting_commit_sha=resulting_commit_sha,
                failure_classification=error.classification,
                failure_detail=error.detail[:MAX_FAILURE_DETAIL],
                now=now,
            )
            if failed is None:
                raise RepositoryOperationConflictError(
                    "Repository operation failure finalization conflicted."
                )
            await self._event(
                session,
                context=context,
                operation=failed,
                history=(
                    RepositoryOperationEventType.RECONCILIATION_REQUIRED
                    if reconciliation
                    else RepositoryOperationEventType.FAILED
                ),
                business=(
                    EventType.ENGINEERING_REPOSITORY_OPERATION_RECONCILIATION_REQUIRED
                    if reconciliation
                    else EventType.ENGINEERING_REPOSITORY_OPERATION_FAILED
                ),
                now=now,
            )
            return failed

    async def _mark_reconciliation_after_commit(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation: RepositoryOperationRecord,
        commit_sha: str,
        now: datetime,
    ) -> None:
        error = RepositoryOperationGitError(
            "persistence_finalization_uncertain",
            "Commit exists but durable finalization did not complete.",
        )
        await self._finalize_failure(
            session,
            context=context,
            operation=operation,
            error=error,
            reconciliation=True,
            resulting_commit_sha=commit_sha,
            now=now,
        )

    def _validate_preflight(
        self,
        adapter: BoundedGitAdapter,
        operation: RepositoryOperationRecord,
    ) -> None:
        state = adapter.inspect_repository_state()
        if state.branch != operation.expected_branch:
            raise RepositoryOperationGitError(
                "branch_mismatch", "Repository branch does not match authorization."
            )
        if state.head != operation.expected_base_commit:
            raise RepositoryOperationGitError(
                "base_commit_mismatch",
                "Repository HEAD does not match authorization.",
            )
        if state.staged_files:
            raise RepositoryOperationGitError(
                "index_not_empty", "Repository index is not empty."
            )
        if state.ignored_files:
            raise RepositoryOperationGitError(
                "ignored_files_present",
                "Repository contains ignored files outside the operation boundary.",
            )
        if state.missing_files:
            raise RepositoryOperationGitError(
                "authorized_file_missing", "An authorized file is missing."
            )
        if state.changed_files != operation.file_boundary:
            raise RepositoryOperationGitError(
                "file_boundary_mismatch",
                "Repository changes do not match authorization.",
            )

    def _validate_staged(
        self,
        adapter: BoundedGitAdapter,
        operation: RepositoryOperationRecord,
    ) -> None:
        state = adapter.inspect_staged_state()
        if state.staged_files != operation.file_boundary:
            raise RepositoryOperationGitError(
                "staged_boundary_mismatch",
                "Staged changes do not match authorization.",
            )
        if state.changed_files != operation.file_boundary:
            raise RepositoryOperationGitError(
                "working_boundary_changed",
                "Repository changed while staging.",
            )
        adapter.validate_staged_content()

    def _validate_post_commit(
        self,
        adapter: BoundedGitAdapter,
        operation: RepositoryOperationRecord,
        commit_sha: str,
    ) -> None:
        commit = adapter.inspect_commit(commit_sha)
        self._validate_commit(operation, commit)
        state = adapter.inspect_repository_state()
        if state.head != commit_sha or state.changed_files or state.staged_files:
            raise RepositoryOperationGitError(
                "post_commit_state_mismatch",
                "Repository state failed post-commit verification.",
            )

    @staticmethod
    def _validate_commit(operation, commit) -> None:
        if (
            commit.parent != operation.expected_base_commit
            or commit.subject != operation.commit_subject
            or commit.files != operation.file_boundary
        ):
            raise RepositoryOperationGitError(
                "commit_verification_failed",
                "Created commit does not match authorization.",
            )

    @staticmethod
    def _authorization_command(
        command: ExecuteRepositoryCommit,
        operation,
    ) -> ValidateRepositoryAuthorization:
        return ValidateRepositoryAuthorization(
            authorization_id=command.authorization_id,
            capability_id=command.capability_id,
            authorization_digest=command.authorization_digest,
            operation_type=AuthorizationOperationType.CREATE_COMMIT,
            file_boundary=operation.file_boundary,
            expected_branch=operation.expected_branch,
            expected_base_commit=operation.expected_base_commit,
        )

    @staticmethod
    def _synthetic_operation(authorization, command, now):
        return RepositoryOperationRecord(
            id=UUID(int=0),
            company_id=authorization.company_id,
            authorization_id=authorization.id,
            command_id=authorization.command_id,
            execution_id=authorization.execution_id,
            review_decision_id=authorization.review_decision_id,
            requested_by_user_id=authorization.authorized_by_user_id,
            operation_type=RepositoryOperationType.CREATE_COMMIT,
            commit_subject=command.commit_subject,
            expected_branch=authorization.expected_branch,
            expected_base_commit=authorization.expected_base_commit,
            file_boundary=authorization.file_boundary,
            boundary_digest="",
            idempotency_key=command.idempotency_key,
            state=RepositoryOperationState.REQUESTED,
            resulting_commit_sha=None,
            failure_classification=None,
            failure_detail=None,
            version=1,
            requested_at=now,
            reserved_at=None,
            execution_started_at=None,
            succeeded_at=None,
            failed_at=None,
            reconciliation_required_at=None,
            updated_at=now,
        )

    @staticmethod
    def _subject(subject: str) -> str:
        if (
            subject != subject.strip()
            or not subject
            or len(subject) > MAX_SUBJECT_LENGTH
            or CONTROL_CHARACTER.search(subject)
        ):
            raise RepositoryOperationValidationError("Commit subject is invalid.")
        return subject

    @staticmethod
    def _idempotency(value: str) -> None:
        if IDEMPOTENCY_KEY.fullmatch(value) is None:
            raise RepositoryOperationValidationError("Idempotency key is invalid.")

    @staticmethod
    def _boundary_digest(boundary: tuple[str, ...]) -> str:
        return hashlib.sha256(
            json.dumps(boundary, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _match_request(
        operation: RepositoryOperationRecord,
        command: ExecuteRepositoryCommit,
        *,
        subject: str | None = None,
    ) -> None:
        if (
            operation.authorization_id != command.authorization_id
            or operation.idempotency_key != command.idempotency_key
            or (subject is not None and operation.commit_subject != subject)
        ):
            raise RepositoryOperationConflictError(
                "Repository operation request conflicts with reservation."
            )

    def _adapter(self) -> BoundedGitAdapter:
        if self.adapter is None:
            raise RepositoryOperationStateError(
                "Repository operation adapter is not configured."
            )
        return self.adapter

    def _require(self, context: AuthorizationContext, permission: str) -> None:
        try:
            self.authorization.require_permission(context, permission)
        except PermissionDeniedError as error:
            raise RepositoryOperationPermissionError(
                "Repository operation is not available."
            ) from error

    async def _event(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        operation: RepositoryOperationRecord,
        history: RepositoryOperationEventType,
        business: EventType,
        now: datetime,
    ) -> None:
        await self.repository.append_event(
            session,
            operation=operation,
            actor_user_id=context.user.id,
            event_type=history,
            now=now,
        )
        safe: dict[str, object] = {
            "operation_id": str(operation.id),
            "authorization_id": str(operation.authorization_id),
            "command_id": str(operation.command_id),
            "operation_type": operation.operation_type.value,
            "state": operation.state.value,
            "version": operation.version,
            "resulting_commit_sha": operation.resulting_commit_sha,
            "failure_classification": operation.failure_classification,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=business.value,
                resource_type="engineering_repository_operation",
                company_id=context.company.id,
                resource_id=operation.id,
                details=safe,
                occurred_at=now,
            ),
        )
        self.events.stage(
            session,
            BusinessEventCreate(
                event_type=business,
                entity_type="engineering_repository_operation",
                entity_id=operation.id,
                company_id=context.company.id,
                payload=safe,
                occurred_at=now,
            ),
        )


def production_repository_operation_service() -> EngineeringRepositoryOperationService:
    root = settings.repository_operation_root
    adapter = (
        ProductionBoundedGitAdapter(Path(root))
        if root is not None and root.strip()
        else None
    )
    return EngineeringRepositoryOperationService(adapter=adapter)
