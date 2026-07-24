from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringCommandRecord,
    EngineeringExecutionState as CommandExecutionState,
)
from app.engineering_control.repository import (
    EngineeringCommandRepository,
    engineering_command_repository,
)
from app.engineering_execution.adapters import (
    EngineeringExecutionAdapterRegistry,
    engineering_execution_adapter_registry,
)
from app.engineering_execution.contracts import (
    EngineeringExecutionRequest,
    EngineeringExecutionResult,
)
from app.engineering_execution.errors import (
    EngineeringExecutionCommandNotFoundError,
    EngineeringExecutionConflictError,
    EngineeringExecutionIneligibleError,
    EngineeringExecutionPermissionError,
)
from app.engineering_execution.records import (
    CreateEngineeringExecution,
    EngineeringExecutionRecord,
)
from app.engineering_execution.repository import EngineeringExecutionRepository
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
from app.platform.permissions.codes import EngineeringExecutionPermission


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringExecutionService:
    def __init__(
        self,
        *,
        repository: type[
            EngineeringExecutionRepository
        ] = EngineeringExecutionRepository,
        command_repository: EngineeringCommandRepository = engineering_command_repository,
        adapters: EngineeringExecutionAdapterRegistry = (
            engineering_execution_adapter_registry
        ),
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
        business_events: type[BusinessEventService] = BusinessEventService,
        provider_identifier: str | None = None,
    ) -> None:
        self.repository = repository
        self.command_repository = command_repository
        self.adapters = adapters
        self.authorization = authorization
        self.audit = audit
        self.business_events = business_events
        self.provider_identifier = provider_identifier

    async def request_execution(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command_id: UUID,
        now: datetime | None = None,
    ) -> EngineeringExecutionResult:
        self._require(context)
        occurred_at = now or utc_now()
        try:
            async with session.begin():
                command = await self.command_repository.get_command_for_update(
                    session,
                    company_id=context.company.id,
                    command_id=command_id,
                )
                if command is None:
                    raise EngineeringExecutionCommandNotFoundError(
                        "Engineering Command was not found."
                    )
                self._validate_command(command, now=occurred_at)
                existing = await self.repository.get_by_command(
                    session,
                    company_id=context.company.id,
                    command_id=command.id,
                )
                if existing is not None:
                    return self._result(existing)
                request = self._request(command)
                provider_identifier = self.provider_identifier or "unassigned"
                adapter = (
                    self.adapters.resolve(provider_identifier)
                    if self.provider_identifier
                    else None
                )
                readiness = (
                    await adapter.validate_readiness() if adapter is not None else None
                )
                record = await self.repository.create(
                    session,
                    execution=CreateEngineeringExecution(
                        company_id=context.company.id,
                        command_id=command.id,
                        ecid=command.ecid,
                        instruction_digest=command.instruction_digest,
                        requested_by_user_id=context.user.id,
                        provider_identifier=provider_identifier,
                        correlation_id=command.correlation_id,
                        requested_at=occurred_at,
                        evidence_summary={
                            "execution_connected": False,
                            "request_digest": request.request_digest,
                            "expected_head": request.expected_head,
                            "adapter_registered": adapter is not None,
                        },
                        validation_summary={
                            "validation_started": False,
                            "adapter_ready": readiness.ready
                            if readiness is not None
                            else False,
                            "readiness_reason": readiness.reason_code
                            if readiness is not None
                            else "provider_not_registered",
                        },
                    ),
                )
                self._stage_evidence(
                    session,
                    context=context,
                    command=command,
                    record=record,
                    occurred_at=occurred_at,
                )
            return self._result(record)
        except IntegrityError as error:
            await session.rollback()
            raise EngineeringExecutionConflictError(
                "An execution request already exists for this command."
            ) from error

    async def get_execution(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        execution_id: UUID,
    ) -> EngineeringExecutionRecord:
        self._require(context)
        async with session.begin():
            record = await self.repository.get(
                session, company_id=context.company.id, execution_id=execution_id
            )
        if record is None:
            raise EngineeringExecutionCommandNotFoundError(
                "Engineering Execution was not found."
            )
        return record

    @staticmethod
    def _request(command: EngineeringCommandRecord) -> EngineeringExecutionRequest:
        return EngineeringExecutionRequest(
            command_id=command.id,
            ecid=command.ecid,
            repository_key=command.repository_key,
            expected_repository_baseline=command.expected_head,
            expected_branch=command.expected_branch,
            expected_head=command.expected_head,
            authorized_code_changes=command.requested_code_changes,
            instruction=command.owner_instruction,
            instruction_digest=command.instruction_digest,
            request_digest=command.request_digest,
            correlation_id=command.correlation_id,
        )

    @staticmethod
    def _validate_command(command: EngineeringCommandRecord, *, now: datetime) -> None:
        if command.approval_state is not EngineeringApprovalState.APPROVED:
            raise EngineeringExecutionIneligibleError(
                "Engineering Command is not approved."
            )
        if command.expires_at <= now:
            raise EngineeringExecutionIneligibleError(
                "Engineering Command has expired."
            )
        if command.execution_state is not CommandExecutionState.EXECUTION_NOT_CONNECTED:
            raise EngineeringExecutionIneligibleError(
                "Engineering Command execution state is ineligible."
            )

    def _require(self, context: AuthorizationContext) -> None:
        if context.membership.status != "active":
            raise EngineeringExecutionPermissionError("Permission denied.")
        try:
            self.authorization.require_permission(
                context, EngineeringExecutionPermission.REQUEST
            )
        except PermissionDeniedError as error:
            raise EngineeringExecutionPermissionError("Permission denied.") from error

    def _stage_evidence(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: EngineeringCommandRecord,
        record: EngineeringExecutionRecord,
        occurred_at: datetime,
    ) -> None:
        safe: dict[str, object] = {
            "execution_id": str(record.id),
            "command_id": str(command.id),
            "ecid": command.ecid,
            "repository_key": command.repository_key,
            "expected_head": command.expected_head,
            "instruction_digest": command.instruction_digest,
            "request_digest": command.request_digest,
            "execution_state": record.state.value,
            "provider_identifier": record.provider_identifier,
        }
        self.audit.stage(
            session,
            AuditEntry(
                action="engineering.execution_requested",
                resource_type="engineering_execution",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=record.id,
                correlation_id=record.correlation_id,
                details=safe,
                occurred_at=occurred_at,
            ),
        )
        self.business_events.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.ENGINEERING_EXECUTION_REQUESTED,
                entity_type="engineering_execution",
                entity_id=record.id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=safe,
                correlation_id=record.correlation_id,
                occurred_at=occurred_at,
            ),
        )

    @staticmethod
    def _result(record: EngineeringExecutionRecord) -> EngineeringExecutionResult:
        return EngineeringExecutionResult(
            execution_id=record.id,
            state=record.state,
            status=record.status,
            started_at=record.started_at,
            finished_at=record.finished_at,
            provider_identifier=record.provider_identifier,
            evidence_summary=record.evidence_summary,
            validation_summary=record.validation_summary,
            output_references=record.output_references,
            failure_classification=record.failure_classification,
        )


engineering_execution_service = EngineeringExecutionService()
