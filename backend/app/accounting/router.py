from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.errors import (
    AccountingConflict,
    AccountingNotFound,
    AccountingPermissionDenied,
    AccountingValidation,
)
from app.accounting.models import OpeningControlException, OpeningControlPackage
from app.accounting.opening_controls import (
    ControlExceptionView,
    OpeningControlApply,
    OpeningControlDetail,
    OpeningControlPage,
    OpeningControlPreview,
    OpeningControlPreviewRequest,
    OpeningControlResponse,
    OpeningControlTransition,
    SealedOpeningPackageSelection,
    opening_control_service,
    preview_opening_controls,
)
from app.accounting.opening_source_adapter import SealedOpeningPackageAdapter
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
from app.core.config import settings
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure
from app.platform.users.models import User

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
ReconcileContext = Annotated[
    AuthorizationContext, Depends(require_permission(AccountingPermission.RECONCILE))
]
OpeningApproveContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AccountingPermission.OPENING_STATE_APPROVE)),
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


@router.post("/opening-controls/sealed-preview", response_model=OpeningControlPreview)
async def preview_sealed_opening_state_controls(
    data: SealedOpeningPackageSelection,
    context: ReconcileContext,
) -> OpeningControlPreview:
    """Preview server-owned sealed evidence; accepts no client calculations."""
    del context
    if not settings.qbo_production_evidence_root:
        raise translate(AccountingNotFound("QBO source custody is not configured"))
    try:
        request = SealedOpeningPackageAdapter(
            Path(settings.qbo_production_evidence_root)
        ).resolve(data.package_identity)
        return preview_opening_controls(request)
    except (AccountingNotFound, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/opening-controls/sealed",
    response_model=OpeningControlResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_sealed_opening_state_controls(
    data: SealedOpeningPackageSelection,
    context: ReconcileContext,
    session: DatabaseSession,
) -> OpeningControlResponse:
    if not settings.qbo_production_evidence_root:
        raise translate(AccountingNotFound("QBO source custody is not configured"))
    try:
        request = SealedOpeningPackageAdapter(
            Path(settings.qbo_production_evidence_root)
        ).resolve(data.package_identity)
        preview = preview_opening_controls(request)
        async with session.begin():
            row = await opening_control_service.submit(
                session,
                context=context,
                request=request,
                expected_digest=preview.evidence_digest,
            )
        return OpeningControlResponse.model_validate(row)
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.get("/opening-controls/{package_id}", response_model=OpeningControlDetail)
async def opening_state_control_detail(
    package_id: UUID, context: ReadContext, session: DatabaseSession
) -> OpeningControlDetail:
    row = await session.scalar(
        select(OpeningControlPackage).where(
            OpeningControlPackage.company_id == context.company.id,
            OpeningControlPackage.id == package_id,
        )
    )
    if row is None:
        raise translate(AccountingNotFound("Opening control package was not found"))
    snapshot = OpeningControlPreviewRequest.model_validate(row.evidence_snapshot)
    actor_ids = tuple(
        value
        for value in (row.prepared_by_user_id, row.approved_by_user_id)
        if value is not None
    )
    actor_rows = (
        await session.execute(
            select(User.id, User.display_name).where(User.id.in_(actor_ids))
        )
    ).all()
    actor_names: dict[UUID, str] = {
        actor_id: display_name for actor_id, display_name in actor_rows
    }
    lifecycle: list[dict[str, object]] = [
        {
            "state": "PREVIEWED",
            "at": row.created_at,
            "actor_role": "preparer",
            "actor_display_name": actor_names.get(
                row.prepared_by_user_id, "Unavailable"
            ),
        }
    ]
    lifecycle.append(
        {
            "state": "READY_FOR_REVIEW"
            if row.status == "READY_FOR_APPROVAL"
            else row.status,
            "at": row.applied_at or row.approved_at or row.created_at,
            "actor_role": "system" if row.status == "REVIEW_REQUIRED" else "reviewer",
            "actor_display_name": (
                actor_names.get(row.approved_by_user_id, "Pending")
                if row.approved_by_user_id
                else "Pending"
            ),
        }
    )
    return OpeningControlDetail(
        package=OpeningControlResponse.model_validate(row),
        trial_balance=snapshot.trial_balance,
        total_debits=row.total_debits,
        total_credits=row.total_credits,
        difference=row.total_debits - row.total_credits,
        equity_categories=tuple(
            sorted(
                {
                    line.equity_category
                    for line in snapshot.trial_balance
                    if line.equity_category
                }
            )
        ),
        ar_difference=(
            row.ar_control_balance - row.ar_subledger_balance
            if row.ar_control_balance is not None
            and row.ar_subledger_balance is not None
            else None
        ),
        ap_difference=(
            row.ap_control_balance - row.ap_subledger_balance
            if row.ap_control_balance is not None
            and row.ap_subledger_balance is not None
            else None
        ),
        source_as_of=row.source_as_of,
        cutoff_at=row.cutoff_at,
        lifecycle=tuple(lifecycle),
    )


@router.get(
    "/opening-controls/{package_id}/subledger/{family}",
    response_model=OpeningControlPage,
)
async def opening_state_subledger_detail(
    package_id: UUID,
    family: Literal["ar", "ap"],
    context: ReadContext,
    session: DatabaseSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> OpeningControlPage:
    row = await session.scalar(
        select(OpeningControlPackage).where(
            OpeningControlPackage.company_id == context.company.id,
            OpeningControlPackage.id == package_id,
        )
    )
    if row is None:
        raise translate(AccountingNotFound("Opening control package was not found"))
    snapshot = OpeningControlPreviewRequest.model_validate(row.evidence_snapshot)
    values = snapshot.source_ar if family == "ar" else snapshot.source_ap
    ordered = sorted(
        values,
        key=lambda item: (
            item.party_identity,
            item.document_identity,
            item.source_identity,
        ),
    )
    items = tuple(
        item.model_dump(mode="json") for item in ordered[offset : offset + limit]
    )
    return OpeningControlPage(
        package_id=row.id, items=items, offset=offset, limit=limit, total=len(ordered)
    )


@router.get(
    "/opening-controls/{package_id}/exceptions",
    response_model=tuple[ControlExceptionView, ...],
)
async def opening_state_control_exceptions(
    package_id: UUID,
    context: ReadContext,
    session: DatabaseSession,
) -> tuple[ControlExceptionView, ...]:
    package = await session.scalar(
        select(OpeningControlPackage.id).where(
            OpeningControlPackage.company_id == context.company.id,
            OpeningControlPackage.id == package_id,
        )
    )
    if package is None:
        raise translate(AccountingNotFound("Opening control package was not found"))
    rows = await session.scalars(
        select(OpeningControlException)
        .where(
            OpeningControlException.company_id == context.company.id,
            OpeningControlException.package_id == package_id,
        )
        .order_by(
            OpeningControlException.control_family,
            OpeningControlException.exception_identity,
        )
    )
    return tuple(ControlExceptionView.model_validate(row) for row in rows.all())


@router.post(
    "/opening-controls/{package_id}/approve",
    response_model=OpeningControlResponse,
)
async def approve_opening_state_controls(
    package_id: UUID,
    data: OpeningControlTransition,
    context: OpeningApproveContext,
    session: DatabaseSession,
) -> OpeningControlResponse:
    try:
        async with session.begin():
            row = await opening_control_service.approve(
                session, context=context, package_id=package_id, transition=data
            )
        return OpeningControlResponse.model_validate(row)
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error


@router.post(
    "/opening-controls/{package_id}/apply",
    response_model=OpeningControlResponse,
)
async def apply_opening_state_controls(
    package_id: UUID,
    data: OpeningControlApply,
    context: OpeningApproveContext,
    session: DatabaseSession,
) -> OpeningControlResponse:
    try:
        async with session.begin():
            row = await opening_control_service.mark_applied(
                session,
                context=context,
                package_id=package_id,
                journal_id=data.journal_id,
                transition=data,
            )
        return OpeningControlResponse.model_validate(row)
    except (AccountingNotFound, AccountingConflict, AccountingValidation) as error:
        raise translate(error) from error
