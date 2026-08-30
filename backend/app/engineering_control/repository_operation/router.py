from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EngineeringRepositoryOperationPermission,
)
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

from .contracts import RepositoryOperationState
from .errors import (
    RepositoryOperationConflictError,
    RepositoryOperationError,
    RepositoryOperationNotFoundError,
    RepositoryOperationPermissionError,
    RepositoryOperationReconciliationRequiredError,
)
from .records import ExecuteRepositoryCommit
from .schemas import (
    ExecuteRepositoryCommitRequest,
    RepositoryOperationDetail,
    RepositoryOperationList,
    RepositoryOperationReadinessResponse,
    RepositoryOperationSummary,
)
from .service import (
    EngineeringRepositoryOperationService,
    production_repository_operation_service,
)

router = APIRouter(
    prefix="/api/v1/engineering/repository-operations",
    tags=["Engineering Repository Operations"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringRepositoryOperationPermission.READ)),
]
ExecuteContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringRepositoryOperationPermission.EXECUTE)),
]


def get_repository_operation_service() -> EngineeringRepositoryOperationService:
    return production_repository_operation_service()


OperationService = Annotated[
    EngineeringRepositoryOperationService,
    Depends(get_repository_operation_service),
]


def _error(error: RepositoryOperationError) -> HTTPException:
    if isinstance(
        error,
        (RepositoryOperationNotFoundError, RepositoryOperationPermissionError),
    ):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Repository operation was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_404_NOT_FOUND, failure.detail())
    if isinstance(error, RepositoryOperationReconciliationRequiredError):
        failure = SafeFailure(
            FailureCode.RECONCILIATION_REQUIRED,
            "Repository operation requires reconciliation.",
            ClientRecovery.RECONCILIATION_REQUIRED,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    if isinstance(error, RepositoryOperationConflictError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Repository operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status.HTTP_409_CONFLICT, failure.detail())
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Repository operation request requires correction.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, failure.detail())


def _summary(record) -> RepositoryOperationSummary:
    return RepositoryOperationSummary.model_validate(record)


def _detail(record) -> RepositoryOperationDetail:
    values = {
        field: getattr(record, field)
        for field in RepositoryOperationDetail.model_fields
        if field != "owner_attention_required"
    }
    return RepositoryOperationDetail.model_validate(
        {
            **values,
            "owner_attention_required": record.state
            in {
                RepositoryOperationState.FAILED,
                RepositoryOperationState.RECONCILIATION_REQUIRED,
            },
        }
    )


@router.post("/execute", response_model=RepositoryOperationDetail)
async def execute_commit(
    data: ExecuteRepositoryCommitRequest,
    context: ExecuteContext,
    session: DatabaseSession,
    service: OperationService,
) -> RepositoryOperationDetail:
    try:
        record = await service.execute(
            session,
            context=context,
            command=ExecuteRepositoryCommit(**data.model_dump()),
        )
    except RepositoryOperationError as error:
        raise _error(error) from error
    return _detail(record)


@router.post("/readiness", response_model=RepositoryOperationReadinessResponse)
async def inspect_readiness(
    data: ExecuteRepositoryCommitRequest,
    context: ExecuteContext,
    session: DatabaseSession,
    service: OperationService,
) -> RepositoryOperationReadinessResponse:
    try:
        readiness = await service.readiness(
            session,
            context=context,
            command=ExecuteRepositoryCommit(**data.model_dump()),
        )
    except RepositoryOperationError as error:
        raise _error(error) from error
    return RepositoryOperationReadinessResponse.model_validate(readiness)


@router.get("", response_model=RepositoryOperationList)
async def list_operations(
    context: ReadContext,
    session: DatabaseSession,
    service: OperationService,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RepositoryOperationList:
    try:
        records = await service.list(session, context=context, limit=limit)
    except RepositoryOperationError as error:
        raise _error(error) from error
    return RepositoryOperationList(items=tuple(_summary(item) for item in records))


@router.get("/{operation_id}", response_model=RepositoryOperationDetail)
async def get_operation(
    operation_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
    service: OperationService,
) -> RepositoryOperationDetail:
    try:
        record = await service.get(session, context=context, operation_id=operation_id)
    except RepositoryOperationError as error:
        raise _error(error) from error
    return _detail(record)


@router.post(
    "/{operation_id}/reconcile",
    response_model=RepositoryOperationDetail,
)
async def reconcile_operation(
    operation_id: UUID,
    data: ExecuteRepositoryCommitRequest,
    context: ExecuteContext,
    session: DatabaseSession,
    service: OperationService,
) -> RepositoryOperationDetail:
    try:
        record = await service.reconcile(
            session,
            context=context,
            command=ExecuteRepositoryCommit(**data.model_dump()),
            operation_id=operation_id,
        )
    except RepositoryOperationError as error:
        raise _error(error) from error
    return _detail(record)
