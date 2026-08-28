"""Authenticated HTTP boundary for Workday Time authority."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import (
    ResolvedAuthorization,
    require_permission,
)

from .commands import CorrectTimeEntry, RecordManualTime, RecordPunch
from .contracts import (
    WorkdayAuthorizationError,
    WorkdayConflictError,
    WorkdayTimeError,
)
from .permissions import TimekeepingPermission
from .query_service import workday_time_queries
from .repository import timekeeping_repository
from .schemas import (
    CorrectionInput,
    ManualTimeInput,
    PayPeriodView,
    PayrollTimeInputView,
    PunchInput,
    PunchResult,
    PunchState,
    TimecardView,
    TimeEntryView,
)
from .service import workday_time_service

router = APIRouter(prefix="/api/v1/timekeeping", tags=["Workday Time"])
Session = Annotated[AsyncSession, Depends(get_database_session)]
OwnPunch = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.OWN_PUNCH))
]
OwnRead = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.OWN_READ))
]
ManualEntry = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.MANUAL_ENTRY))
]
Correct = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.CORRECT))
]
Approve = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.APPROVE))
]
AdminRead = Annotated[
    AuthorizationContext, Depends(require_permission(TimekeepingPermission.ADMIN_READ))
]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description="Opaque client-generated retry identity",
    ),
]


def _error(value: WorkdayTimeError | WorkdayAuthorizationError) -> HTTPException:
    if isinstance(value, WorkdayAuthorizationError):
        return HTTPException(status.HTTP_403_FORBIDDEN, str(value))
    if isinstance(value, WorkdayConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, str(value))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(value))


def _branch_and_timezone(context: AuthorizationContext) -> tuple[UUID | None, str]:
    if context.active_branch is None:
        return None, context.company.timezone
    return context.active_branch.id, context.active_branch.timezone


@router.post("/me/punches", response_model=PunchResult)
async def punch(
    payload: PunchInput,
    idempotency_key: IdempotencyKey,
    context: OwnPunch,
    session: Session,
) -> PunchResult:
    try:
        employee = await workday_time_queries.self_employee(session, context)
        branch_id, timezone_name = _branch_and_timezone(context)
        event, completed = await workday_time_service.record_punch(
            session,
            context=context,
            command=RecordPunch(
                employee_id=employee.id,
                branch_id=branch_id,
                kind=payload.action,
                occurred_at=datetime.now(timezone.utc),
                timezone=timezone_name,
                idempotency_key=idempotency_key,
                source_device_reference=payload.device_reference,
            ),
        )
        current = await workday_time_queries.state(
            session, context=context, employee_id=employee.id
        )
        return PunchResult(
            punch_id=event.id,
            action=payload.action,
            occurred_at=event.occurred_at,
            state=current,
            completed_entry=(
                workday_time_queries.entry_view(completed)
                if completed is not None
                else None
            ),
        )
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.get("/me/state", response_model=PunchState)
async def own_state(context: OwnRead, session: Session) -> PunchState:
    try:
        employee = await workday_time_queries.self_employee(session, context)
        return await workday_time_queries.state(
            session, context=context, employee_id=employee.id
        )
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.get("/me/timecard", response_model=TimecardView)
async def own_timecard(context: OwnRead, session: Session) -> TimecardView:
    try:
        return await workday_time_queries.own_timecard(session, context=context)
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.post("/entries/manual", response_model=TimeEntryView)
async def manual_entry(
    payload: ManualTimeInput,
    idempotency_key: IdempotencyKey,
    context: ManualEntry,
    session: Session,
) -> TimeEntryView:
    try:
        branch_id, _ = _branch_and_timezone(context)
        result = await workday_time_service.record_manual_time(
            session,
            context=context,
            command=RecordManualTime(
                employee_id=payload.employee_id,
                branch_id=branch_id,
                work_date=payload.work_date,
                timezone=payload.timezone,
                start_at=payload.start_at,
                end_at=payload.end_at,
                approved_duration_minutes=payload.approved_duration_minutes,
                reason=payload.reason,
                idempotency_key=idempotency_key,
            ),
        )
        return workday_time_queries.entry_view(result)
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.post("/entries/{revision_id}/corrections", response_model=TimeEntryView)
async def correct_entry(
    revision_id: UUID,
    payload: CorrectionInput,
    context: Correct,
    session: Session,
) -> TimeEntryView:
    try:
        result = await workday_time_service.correct(
            session,
            context=context,
            command=CorrectTimeEntry(
                revision_id=revision_id,
                start_at=payload.start_at,
                end_at=payload.end_at,
                approved_duration_minutes=payload.approved_duration_minutes,
                reason=payload.reason,
            ),
        )
        return workday_time_queries.entry_view(result)
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.post("/entries/{revision_id}/submit", response_model=TimeEntryView)
async def submit_entry(
    revision_id: UUID,
    context: ResolvedAuthorization,
    session: Session,
) -> TimeEntryView:
    try:
        result = await workday_time_service.submit(
            session, context=context, revision_id=revision_id
        )
        return workday_time_queries.entry_view(result)
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.post("/entries/{revision_id}/approve", response_model=TimeEntryView)
async def approve_entry(
    revision_id: UUID,
    context: Approve,
    session: Session,
) -> TimeEntryView:
    try:
        result = await workday_time_service.approve(
            session, context=context, revision_id=revision_id
        )
        return workday_time_queries.entry_view(result)
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error


@router.get("/pay-periods/current", response_model=PayPeriodView | None)
async def current_pay_period(context: AdminRead, session: Session) -> PayPeriodView | None:
    _, timezone_name = _branch_and_timezone(context)
    today = datetime.now(timezone.utc).astimezone(ZoneInfo(timezone_name)).date()
    value = await timekeeping_repository.pay_period_for_date(
        session, company_id=context.company.id, work_date=today
    )
    return workday_time_queries.pay_period_view(value) if value is not None else None


@router.get("/pay-periods/{pay_period_id}", response_model=PayPeriodView)
async def pay_period(
    pay_period_id: UUID, context: AdminRead, session: Session
) -> PayPeriodView:
    value = await timekeeping_repository.pay_period_by_id(
        session, company_id=context.company.id, pay_period_id=pay_period_id
    )
    if value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pay period not found.")
    return workday_time_queries.pay_period_view(value)


@router.post(
    "/pay-periods/{pay_period_id}/employees/{employee_id}/payroll-time-input",
    response_model=PayrollTimeInputView,
)
async def seal_payroll_time_input(
    pay_period_id: UUID,
    employee_id: UUID,
    context: Approve,
    session: Session,
) -> PayrollTimeInputView:
    period = await timekeeping_repository.pay_period_by_id(
        session, company_id=context.company.id, pay_period_id=pay_period_id
    )
    if period is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pay period not found.")
    try:
        value = await workday_time_service.seal_payroll_input(
            session, context=context, employee_id=employee_id, pay_period=period
        )
        return PayrollTimeInputView(
            snapshot_id=value.snapshot_id,
            version=value.version,
            employee_id=value.employee_id,
            pay_period_id=value.pay_period_id,
            period_start=value.period_start,
            period_end=value.period_end,
            approved_revision_ids=tuple(
                item.revision_id for item in value.approved_entries
            ),
            total_approved_minutes=value.total_approved_minutes,
            snapshot_digest=value.snapshot_digest,
        )
    except (WorkdayTimeError, WorkdayAuthorizationError) as error:
        raise _error(error) from error
