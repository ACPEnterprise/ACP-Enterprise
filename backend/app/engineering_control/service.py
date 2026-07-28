from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
    CreateEngineeringCommand,
    EngineeringCommandPage,
    EngineeringCommandQuery,
    ExpireEngineeringCommand,
)
from app.engineering_control.errors import (
    EngineeringCommandApprovalMismatchError,
    EngineeringCommandExpirationError,
    EngineeringCommandExpiredError,
    EngineeringCommandIdempotencyConflictError,
    EngineeringCommandLifecycleError,
    EngineeringCommandNotFoundError,
    EngineeringCommandPermissionError,
    EngineeringCommandRepositoryPolicyError,
    EngineeringCommandStaleVersionError,
    EngineeringCommandUnsafeInstructionError,
    EngineeringCommandValidationError,
)
from app.engineering_control.lifecycle import EngineeringCommandEventType
from app.engineering_control.records import (
    AppendEngineeringCommandEvent,
    EngineeringApprovalState,
    EngineeringCommandMutationResult,
    EngineeringCommandRecord,
    EngineeringMutationStatus,
)
from app.engineering_control.records import (
    CreateEngineeringCommand as CreateEngineeringCommandRecord,
)
from app.engineering_control.registry import (
    EngineeringRepositoryDefinition,
    EngineeringRepositoryRegistry,
    EngineeringRepositoryRegistryError,
    engineering_repository_registry,
)
from app.engineering_control.repository import (
    EngineeringCommandRepository,
    engineering_command_repository,
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
from app.platform.permissions.codes import EngineeringCommandPermission

COMMAND_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
MAX_INSTRUCTION_LENGTH = 12_000
MAX_COMMAND_LIFETIME = timedelta(days=7)
DEFAULT_COMMAND_QUERY = EngineeringCommandQuery()

SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
    re.compile(
        r"\b(password|access[_ -]?token|api[_ -]?key|secret)"
        r"\s*[:=]\s*[^\s]{4,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(expose|print|show|dump)\b.{0,40}\b(credentials?|secrets?)\b", re.IGNORECASE
    ),
)
PRIVILEGED_PATTERNS = (
    re.compile(
        r"\bcommit\s+(these|the|all|my)\s+(changes|files|work)\b", re.IGNORECASE
    ),
    re.compile(r"\bgit\s+(commit|push|merge|rebase|reset)\b", re.IGNORECASE),
    re.compile(r"\bpush\s+(these|the)\s+changes\b", re.IGNORECASE),
    re.compile(r"\bmerge\s+(this|the)\s+(branch|changes)\b", re.IGNORECASE),
    re.compile(r"\bdeploy\s+(this|the|to)\b", re.IGNORECASE),
    re.compile(
        r"\b(delete|remove)\s+(the\s+)?(branch|worktree|infrastructure)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(reset|rewrite)\s+(the\s+)?(branch|history)\b", re.IGNORECASE),
    re.compile(
        r"\b(manage|rotate|create|change)\s+(credentials?|secrets?)\b", re.IGNORECASE
    ),
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringControlService:
    def __init__(
        self,
        *,
        repository: EngineeringCommandRepository = engineering_command_repository,
        registry: EngineeringRepositoryRegistry = engineering_repository_registry,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        business_events: type[BusinessEventService] = BusinessEventService,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.authorization = authorization
        self.audit = audit
        self.business_events = business_events

    async def create_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CreateEngineeringCommand,
        now: datetime | None = None,
    ) -> EngineeringCommandRecord:
        self._require(context, EngineeringCommandPermission.MANAGE)
        occurred_at = now or utc_now()
        normalized = self._normalize_create(
            command,
            company_id=context.company.id,
            requested_by_user_id=context.user.id,
            now=occurred_at,
        )
        try:
            async with session.begin():
                existing = await self.repository.get_command_by_idempotency_key(
                    session,
                    company_id=context.company.id,
                    idempotency_key=normalized.idempotency_key,
                )
                if existing is not None:
                    return self._resolve_idempotent(existing, normalized.request_digest)
                record = await self.repository.create_command(
                    session, command=normalized
                )
                await self._append_event(
                    session,
                    record=record,
                    event_type=EngineeringCommandEventType.CREATED,
                    actor_user_id=context.user.id,
                    occurred_at=occurred_at,
                    prior_approval=None,
                )
                self._stage_evidence(
                    session,
                    context=context,
                    record=record,
                    event_type=EventType.ENGINEERING_COMMAND_CREATED,
                    audit_action="engineering.command_created",
                    occurred_at=occurred_at,
                )
            return record
        except IntegrityError:
            await session.rollback()
            async with session.begin():
                existing = await self.repository.get_command_by_idempotency_key(
                    session,
                    company_id=context.company.id,
                    idempotency_key=normalized.idempotency_key,
                )
                if existing is None:
                    raise
                return self._resolve_idempotent(existing, normalized.request_digest)

    async def approve_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ApproveEngineeringCommand,
        now: datetime | None = None,
    ) -> EngineeringCommandRecord:
        self._require(context, EngineeringCommandPermission.APPROVE)
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self._require_command(
                session, context=context, command_id=command.command_id
            )
            self._validate_approval(current, command, now=occurred_at)
            result = await self.repository.approve_command(
                session,
                company_id=context.company.id,
                command_id=command.command_id,
                expected_version=command.expected_version,
                approved_by_user_id=context.user.id,
                approved_at=occurred_at,
            )
            record = self._resolve_approval_result(
                result, context=context, command=command
            )
            if result.status is not EngineeringMutationStatus.APPLIED:
                return record
            await self._append_event(
                session,
                record=record,
                event_type=EngineeringCommandEventType.APPROVED,
                actor_user_id=context.user.id,
                occurred_at=occurred_at,
                prior_approval=EngineeringApprovalState.AWAITING_APPROVAL,
            )
            self._stage_evidence(
                session,
                context=context,
                record=record,
                event_type=EventType.ENGINEERING_COMMAND_APPROVED,
                audit_action="engineering.command_approved",
                occurred_at=occurred_at,
            )
        return record

    async def cancel_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CancelEngineeringCommand,
        now: datetime | None = None,
    ) -> EngineeringCommandRecord:
        self._require(context, EngineeringCommandPermission.MANAGE)
        if not REASON_CODE.fullmatch(command.reason_code):
            raise EngineeringCommandValidationError(
                "Cancellation reason code is invalid."
            )
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self._require_command(
                session, context=context, command_id=command.command_id
            )
            if (
                current.approval_state is EngineeringApprovalState.CANCELED
                and current.canceled_by_user_id == context.user.id
                and current.cancellation_reason_code == command.reason_code
            ):
                return current
            result = await self.repository.cancel_command(
                session,
                company_id=context.company.id,
                command_id=command.command_id,
                expected_version=command.expected_version,
                canceled_by_user_id=context.user.id,
                canceled_at=occurred_at,
                cancellation_reason_code=command.reason_code,
            )
            record = self._resolve_mutation(result)
            await self._append_event(
                session,
                record=record,
                event_type=EngineeringCommandEventType.CANCELED,
                actor_user_id=context.user.id,
                occurred_at=occurred_at,
                prior_approval=current.approval_state,
                reason_code=command.reason_code,
            )
            self._stage_evidence(
                session,
                context=context,
                record=record,
                event_type=EventType.ENGINEERING_COMMAND_CANCELED,
                audit_action="engineering.command_canceled",
                occurred_at=occurred_at,
                reason_code=command.reason_code,
            )
        return record

    async def expire_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: ExpireEngineeringCommand,
        now: datetime | None = None,
    ) -> EngineeringCommandRecord:
        self._require(context, EngineeringCommandPermission.MANAGE)
        occurred_at = now or utc_now()
        async with session.begin():
            current = await self._require_command(
                session, context=context, command_id=command.command_id
            )
            if current.expires_at > occurred_at:
                raise EngineeringCommandExpirationError(
                    "Engineering Command has not expired."
                )
            result = await self.repository.expire_command(
                session,
                company_id=context.company.id,
                command_id=command.command_id,
                expected_version=command.expected_version,
                expired_at=occurred_at,
            )
            record = self._resolve_mutation(result)
            await self._append_event(
                session,
                record=record,
                event_type=EngineeringCommandEventType.EXPIRED,
                actor_user_id=context.user.id,
                occurred_at=occurred_at,
                prior_approval=current.approval_state,
            )
            self._stage_evidence(
                session,
                context=context,
                record=record,
                event_type=EventType.ENGINEERING_COMMAND_EXPIRED,
                audit_action="engineering.command_expired",
                occurred_at=occurred_at,
            )
        return record

    async def get_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
    ) -> EngineeringCommandRecord:
        self._require(context, EngineeringCommandPermission.READ)
        async with session.begin():
            return await self._require_command(
                session, context=context, command_id=command_id
            )

    async def list_commands(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: EngineeringCommandQuery = DEFAULT_COMMAND_QUERY,
    ) -> EngineeringCommandPage:
        self._require(context, EngineeringCommandPermission.READ)
        if query.page < 1:
            raise EngineeringCommandValidationError("Page must be at least 1.")
        if query.page_size < 1 or query.page_size > 200:
            raise EngineeringCommandValidationError(
                "Page size must be between 1 and 200."
            )
        offset = (query.page - 1) * query.page_size
        async with session.begin():
            result = await self.repository.list_commands(
                session,
                company_id=context.company.id,
                approval_state=query.approval_state,
                offset=offset,
                limit=query.page_size,
            )
        total_pages = (
            (result.total_count + query.page_size - 1) // query.page_size
            if result.total_count
            else 0
        )
        return EngineeringCommandPage(
            items=result.items,
            page=query.page,
            page_size=query.page_size,
            total_count=result.total_count,
            total_pages=total_pages,
        )

    def _normalize_create(
        self,
        command: CreateEngineeringCommand,
        *,
        company_id: UUID,
        requested_by_user_id: UUID,
        now: datetime,
    ) -> CreateEngineeringCommandRecord:
        command_type = command.command_type.strip()
        if not COMMAND_TYPE.fullmatch(command_type):
            raise EngineeringCommandValidationError("Command type is invalid.")
        instruction = command.owner_instruction.strip()
        if not instruction or len(instruction) > MAX_INSTRUCTION_LENGTH:
            raise EngineeringCommandValidationError(
                "Owner instruction is blank or too long."
            )
        self._validate_instruction(instruction)
        try:
            repository = self.registry.resolve(command.repository_key.strip())
        except EngineeringRepositoryRegistryError as error:
            raise EngineeringCommandRepositoryPolicyError(
                "Repository is not approved."
            ) from error
        if not self._repository_allows_command(
            repository=repository,
            command_type=command.command_type,
            expected_branch=command.expected_branch,
            requested_code_changes=command.requested_code_changes,
        ):
            raise EngineeringCommandRepositoryPolicyError(
                "Expected branch violates repository policy."
            )
        if not FULL_SHA.fullmatch(command.expected_head):
            raise EngineeringCommandValidationError("Expected HEAD is invalid.")
        if (
            command.requested_code_changes
            and not repository.uncommitted_code_changes_allowed
        ):
            raise EngineeringCommandRepositoryPolicyError(
                "Requested code changes exceed repository policy."
            )
        if command.expires_at.tzinfo is None or command.expires_at <= now:
            raise EngineeringCommandExpirationError("Expiration must be in the future.")
        if command.expires_at > now + MAX_COMMAND_LIFETIME:
            raise EngineeringCommandExpirationError(
                "Expiration exceeds the maximum command lifetime."
            )
        idempotency_key = command.idempotency_key.strip()
        if not IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise EngineeringCommandValidationError("Idempotency key is invalid.")
        instruction_digest = _digest(instruction)
        request_payload = {
            "command_type": command_type,
            "owner_instruction": instruction,
            "repository_key": repository.repository_key,
            "expected_branch": command.expected_branch,
            "expected_head": command.expected_head,
            "requested_code_changes": command.requested_code_changes,
            "expires_at": command.expires_at.isoformat(),
        }
        return CreateEngineeringCommandRecord(
            company_id=company_id,
            requested_by_user_id=requested_by_user_id,
            command_type=command_type,
            owner_instruction=instruction,
            instruction_digest=instruction_digest,
            repository_key=repository.repository_key,
            expected_branch=command.expected_branch,
            expected_head=command.expected_head,
            requested_code_changes=command.requested_code_changes,
            idempotency_key=idempotency_key,
            request_digest=_canonical_digest(request_payload),
            expires_at=command.expires_at,
            created_at=now,
            correlation_id=command.correlation_id or uuid4(),
        )

    @staticmethod
    def _validate_instruction(instruction: str) -> None:
        if any(pattern.search(instruction) for pattern in SECRET_PATTERNS):
            raise EngineeringCommandUnsafeInstructionError(
                "Owner instruction contains prohibited secret-like content."
            )
        if any(pattern.search(instruction) for pattern in PRIVILEGED_PATTERNS):
            raise EngineeringCommandUnsafeInstructionError(
                "Owner instruction requests a prohibited privileged action."
            )
        if re.search(r"(^|[\s\"'])\.\./", instruction):
            raise EngineeringCommandUnsafeInstructionError(
                "Owner instruction contains a prohibited traversal target."
            )

    def _require(self, context: AuthorizationContext, permission: str) -> None:
        if context.membership.status != "active":
            raise EngineeringCommandPermissionError("Permission denied.")
        try:
            self.authorization.require_permission(context, permission)
        except PermissionDeniedError as error:
            raise EngineeringCommandPermissionError("Permission denied.") from error

    async def _require_command(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
    ) -> EngineeringCommandRecord:
        record = await self.repository.get_command(
            session, company_id=context.company.id, command_id=command_id
        )
        if record is None:
            raise EngineeringCommandNotFoundError("Engineering Command was not found.")
        return record

    def _validate_approval(
        self,
        record: EngineeringCommandRecord,
        command: ApproveEngineeringCommand,
        *,
        now: datetime,
    ) -> None:
        if record.instruction_digest != command.instruction_digest:
            raise EngineeringCommandApprovalMismatchError(
                "Instruction digest does not match."
            )
        if (
            record.request_digest != command.request_digest
            or record.repository_key != command.repository_key
        ):
            raise EngineeringCommandApprovalMismatchError(
                "Request digest or repository key does not match."
            )
        if (
            record.expected_branch != command.expected_branch
            or record.expected_head != command.expected_head
            or record.requested_code_changes != command.requested_code_changes
        ):
            raise EngineeringCommandApprovalMismatchError(
                "Repository expectation or permission ceiling does not match."
            )
        if record.approval_state is EngineeringApprovalState.APPROVED:
            return
        if record.expires_at <= now:
            raise EngineeringCommandExpiredError("Engineering Command has expired.")
        try:
            repository = self.registry.resolve(record.repository_key)
        except EngineeringRepositoryRegistryError as error:
            raise EngineeringCommandRepositoryPolicyError(
                "Repository is no longer approved."
            ) from error
        if not self._repository_allows_command(
            repository=repository,
            command_type=record.command_type,
            expected_branch=record.expected_branch,
            requested_code_changes=record.requested_code_changes,
        ):
            raise EngineeringCommandRepositoryPolicyError(
                "Repository policy no longer permits this command."
            )

    @staticmethod
    def _repository_allows_command(
        *,
        repository: EngineeringRepositoryDefinition,
        command_type: str,
        expected_branch: str,
        requested_code_changes: bool,
    ) -> bool:
        active_branch = expected_branch == repository.approved_active_branch
        active_branch_allowed = active_branch and (
            not requested_code_changes or repository.uncommitted_code_changes_allowed
        )
        approved_read_only_inspection = (
            command_type == "inspect_workspace"
            and not requested_code_changes
            and repository.inspection_allowed
            and expected_branch in repository.approved_inspection_branches
        )
        return active_branch_allowed or approved_read_only_inspection

    @staticmethod
    def _resolve_idempotent(
        existing: EngineeringCommandRecord, request_digest: str
    ) -> EngineeringCommandRecord:
        if existing.request_digest != request_digest:
            raise EngineeringCommandIdempotencyConflictError(
                "Idempotency key was already used for another request."
            )
        return existing

    @staticmethod
    def _resolve_mutation(
        result: EngineeringCommandMutationResult,
    ) -> EngineeringCommandRecord:
        if result.status is EngineeringMutationStatus.APPLIED and result.record:
            return result.record
        if result.status is EngineeringMutationStatus.NOT_FOUND:
            raise EngineeringCommandNotFoundError("Engineering Command was not found.")
        if result.status is EngineeringMutationStatus.STALE_VERSION:
            raise EngineeringCommandStaleVersionError(
                "Engineering Command version is stale."
            )
        raise EngineeringCommandLifecycleError(
            "Engineering Command lifecycle transition is not permitted."
        )

    def _resolve_approval_result(
        self,
        result: EngineeringCommandMutationResult,
        *,
        context: AuthorizationContext,
        command: ApproveEngineeringCommand,
    ) -> EngineeringCommandRecord:
        if (
            result.record is not None
            and result.record.approval_state is EngineeringApprovalState.APPROVED
            and result.record.approved_by_user_id == context.user.id
            and result.record.instruction_digest == command.instruction_digest
            and result.record.request_digest == command.request_digest
            and result.record.repository_key == command.repository_key
            and result.record.expected_branch == command.expected_branch
            and result.record.expected_head == command.expected_head
            and result.record.requested_code_changes == command.requested_code_changes
        ):
            return result.record
        return self._resolve_mutation(result)

    async def _append_event(
        self,
        session: AsyncSession,
        *,
        record: EngineeringCommandRecord,
        event_type: EngineeringCommandEventType,
        actor_user_id: UUID | None,
        occurred_at: datetime,
        prior_approval: EngineeringApprovalState | None,
        reason_code: str | None = None,
    ) -> None:
        await self.repository.append_event(
            session,
            event=AppendEngineeringCommandEvent(
                company_id=record.company_id,
                command_id=record.id,
                ecid=record.ecid,
                instruction_digest=record.instruction_digest,
                event_type=event_type.value,
                occurred_at=occurred_at,
                correlation_id=record.correlation_id,
                prior_approval_state=prior_approval,
                new_approval_state=record.approval_state,
                prior_execution_state=record.execution_state,
                new_execution_state=record.execution_state,
                actor_user_id=actor_user_id,
                reason_code=reason_code,
                metadata={
                    "repository_key": record.repository_key,
                    "instruction_digest": record.instruction_digest,
                },
            ),
        )

    def _stage_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: EngineeringCommandRecord,
        event_type: EventType,
        audit_action: str,
        occurred_at: datetime,
        reason_code: str | None = None,
    ) -> None:
        safe: dict[str, object] = {
            "ecid": record.ecid,
            "repository_key": record.repository_key,
            "instruction_digest": record.instruction_digest,
            "request_digest": record.request_digest,
            "approval_state": record.approval_state.value,
            "execution_state": record.execution_state.value,
            "correlation_id": str(record.correlation_id),
            "requested_code_changes": record.requested_code_changes,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action=audit_action,
                resource_type="engineering_command",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=record.id,
                reason_code=reason_code,
                correlation_id=record.correlation_id,
                details=safe,
                occurred_at=occurred_at,
            ),
        )
        self.business_events.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="engineering_command",
                entity_id=record.id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=safe,
                correlation_id=record.correlation_id,
                occurred_at=occurred_at,
            ),
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_digest(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return _digest(serialized)


engineering_control_service = EngineeringControlService()
