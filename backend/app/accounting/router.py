from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingPermissionDenied,
    AccountingValidation,
)
from app.accounting.repository import accounting_repository
from app.accounting.schemas import (
    AccountCreate,
    AccountResponse,
    ChartCreate,
    ChartResponse,
    ControlAssignmentCreate,
    JournalApprove,
    JournalCreate,
    JournalLineResponse,
    JournalResponse,
    JournalTransition,
    PeriodCreate,
    PeriodResponse,
    PeriodTransitionRequest,
    ReversalCreate,
    TrialBalanceResponse,
)
from app.accounting.service import accounting_service
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/accounting", tags=["Accounting"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.READ))
]
PrepareContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.JOURNAL_PREPARE)),
]
PostContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.JOURNAL_POST))
]
PeriodContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.PERIOD_MANAGE)),
]
ReverseContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.JOURNAL_REVERSE)),
]
ReportContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.REPORT_READ))
]


def translate(error: Exception) -> HTTPException:
    if isinstance(error, AccountingNotFound):
        failure = SafeFailure(
            FailureCode.NOT_FOUND,
            "Accounting resource was not found.",
            ClientRecovery.TERMINAL_FAILURE,
            current_correlation_id(),
        )
        return HTTPException(status_code=404, detail=failure.detail())
    if isinstance(error, AccountingConflict):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "Accounting operation conflicts with current authority.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(status_code=409, detail=failure.detail())
    if isinstance(error, AccountingPermissionDenied):
        failure = SafeFailure(
            FailureCode.FORBIDDEN,
            "Accounting operation is not authorized.",
            ClientRecovery.OWNER_ADMIN_ACTION_REQUIRED,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=403,
            detail=failure.detail(),
        )
    failure = SafeFailure(
        FailureCode.VALIDATION,
        "Accounting request violates domain validation rules.",
        ClientRecovery.USER_CORRECTION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status_code=422, detail=failure.detail())


def response(journal: object, lines: tuple[object, ...]) -> JournalResponse:
    values = {
        name: getattr(journal, name)
        for name in JournalResponse.model_fields
        if name != "lines"
    }
    return JournalResponse(
        **values,
        lines=tuple(JournalLineResponse.model_validate(line) for line in lines),
    )


@router.post(
    "/charts", response_model=ChartResponse, status_code=status.HTTP_201_CREATED
)
async def create_chart(
    data: ChartCreate, context: PeriodContext, session: DatabaseSession
) -> ChartResponse:
    try:
        return ChartResponse.model_validate(
            await accounting_service.create_chart(session, context=context, data=data)
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/accounts", response_model=tuple[AccountResponse, ...])
async def list_accounts(
    context: ReadContext, session: DatabaseSession
) -> tuple[AccountResponse, ...]:
    return tuple(
        AccountResponse.model_validate(row)
        for row in await accounting_repository.list_accounts(
            session, context.company.id
        )
    )


@router.post(
    "/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    data: AccountCreate, context: PeriodContext, session: DatabaseSession
) -> AccountResponse:
    try:
        return AccountResponse.model_validate(
            await accounting_service.create_account(session, context=context, data=data)
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/control-accounts", status_code=status.HTTP_201_CREATED)
async def assign_control(
    data: ControlAssignmentCreate, context: PeriodContext, session: DatabaseSession
) -> dict[str, str]:
    try:
        record = await accounting_service.assign_control(
            session, context=context, data=data
        )
        return {"id": str(record.id)}
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/periods", response_model=tuple[PeriodResponse, ...])
async def list_periods(
    context: ReadContext, session: DatabaseSession
) -> tuple[PeriodResponse, ...]:
    return tuple(
        PeriodResponse.model_validate(row)
        for row in await accounting_repository.list_periods(session, context.company.id)
    )


@router.post(
    "/periods", response_model=PeriodResponse, status_code=status.HTTP_201_CREATED
)
async def create_period(
    data: PeriodCreate, context: PeriodContext, session: DatabaseSession
) -> PeriodResponse:
    try:
        return PeriodResponse.model_validate(
            await accounting_service.create_period(session, context=context, data=data)
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/periods/{period_id}/begin-close", response_model=PeriodResponse)
async def begin_close(
    period_id: UUID,
    data: PeriodTransitionRequest,
    context: PeriodContext,
    session: DatabaseSession,
) -> PeriodResponse:
    try:
        return PeriodResponse.model_validate(
            await accounting_service.begin_close(
                session, context=context, period_id=period_id, data=data
            )
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/periods/{period_id}/close", response_model=PeriodResponse)
async def close_period(
    period_id: UUID,
    data: PeriodTransitionRequest,
    context: ReadContext,
    session: DatabaseSession,
) -> PeriodResponse:
    if not context.has_permission(
        AccountingPermission.PERIOD_MANAGE
    ) or not context.has_permission(AccountingPermission.FINANCE_APPROVE):
        raise translate(
            AccountingPermissionDenied(
                "Period close requires period management and Finance approval."
            )
        )
    try:
        return PeriodResponse.model_validate(
            await accounting_service.close_period(
                session, context=context, period_id=period_id, data=data
            )
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/periods/{period_id}/reopen-request", status_code=status.HTTP_202_ACCEPTED
)
async def request_reopen(
    period_id: UUID,
    data: PeriodTransitionRequest,
    context: PeriodContext,
    session: DatabaseSession,
) -> dict[str, str]:
    try:
        transition = await accounting_service.request_reopen(
            session, context=context, period_id=period_id, data=data
        )
        return {"transition_id": str(transition.id)}
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/periods/{period_id}/reopen-approval", response_model=PeriodResponse)
async def approve_reopen(
    period_id: UUID,
    data: PeriodTransitionRequest,
    context: ReadContext,
    session: DatabaseSession,
) -> PeriodResponse:
    if not context.has_permission(AccountingPermission.FINANCE_APPROVE):
        raise translate(
            AccountingPermissionDenied(
                "Period reopen approval requires Finance approval."
            )
        )
    try:
        return PeriodResponse.model_validate(
            await accounting_service.approve_reopen(
                session, context=context, period_id=period_id, data=data
            )
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/journals", response_model=JournalResponse, status_code=status.HTTP_201_CREATED
)
async def create_journal(
    data: JournalCreate, context: PrepareContext, session: DatabaseSession
) -> JournalResponse:
    allow_override = context.has_permission(AccountingPermission.RECONCILE) or (
        data.journal_type == "opening"
        and context.has_permission(AccountingPermission.OPENING_STATE_APPROVE)
    )
    try:
        journal = await accounting_service.create_journal(
            session, context=context, data=data, allow_control_override=allow_override
        )
        return response(
            journal,
            await accounting_repository.lines(session, context.company.id, journal.id),
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/journals/{journal_id}/prepare", response_model=JournalResponse)
async def prepare_journal(
    journal_id: UUID,
    data: JournalTransition,
    context: PrepareContext,
    session: DatabaseSession,
) -> JournalResponse:
    try:
        journal = await accounting_service.prepare_journal(
            session,
            context=context,
            journal_id=journal_id,
            expected_version=data.expected_version,
        )
        return response(
            journal,
            await accounting_repository.lines(session, context.company.id, journal.id),
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/journals/{journal_id}/approve", response_model=JournalResponse)
async def approve_journal(
    journal_id: UUID,
    data: JournalApprove,
    context: PostContext,
    session: DatabaseSession,
) -> JournalResponse:
    try:
        journal = await accounting_service.approve_journal(
            session,
            context=context,
            journal_id=journal_id,
            expected_version=data.expected_version,
            evidence_digest=data.evidence_digest,
            reason=data.reason,
        )
        return response(
            journal,
            await accounting_repository.lines(session, context.company.id, journal.id),
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post("/journals/{journal_id}/post", response_model=JournalResponse)
async def post_journal(
    journal_id: UUID,
    data: JournalTransition,
    context: PostContext,
    session: DatabaseSession,
) -> JournalResponse:
    try:
        journal = await accounting_service.post_journal(
            session,
            context=context,
            journal_id=journal_id,
            expected_version=data.expected_version,
        )
        return response(
            journal,
            await accounting_repository.lines(session, context.company.id, journal.id),
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/journals/{journal_id}/reversals",
    response_model=JournalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def reverse_journal(
    journal_id: UUID,
    data: ReversalCreate,
    context: ReverseContext,
    session: DatabaseSession,
) -> JournalResponse:
    try:
        journal = await accounting_service.reverse_journal(
            session, context=context, journal_id=journal_id, data=data
        )
        return response(
            journal,
            await accounting_repository.lines(session, context.company.id, journal.id),
        )
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/trial-balance", response_model=TrialBalanceResponse)
async def trial_balance(
    context: ReportContext, session: DatabaseSession
) -> TrialBalanceResponse:
    debits, credits = await accounting_repository.trial_balance(
        session, context.company.id
    )
    return TrialBalanceResponse(
        total_debits=debits,
        total_credits=credits,
        net=debits - credits,
        balanced=debits == credits,
    )
