from typing import Annotated, Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.jobs.commands import (
    ActivateJob,
    CancelJob,
    CompleteJob,
    CreateJob,
    CreateJobFromAppointment,
    PauseJob,
    ReopenJob,
    ResumeJob,
    StartJob,
)
from app.jobs.errors import (
    AppointmentAlreadyLinkedError,
    JobCancellationBlockedError,
    JobCompletionBlockedError,
    JobError,
    JobInvalidTransitionError,
    JobNotFoundError,
    JobQueryValidationError,
    JobReferenceNotFoundError,
    JobReopeningBlockedError,
    JobValidationError,
    JobVersionConflictError,
)
from app.jobs.models import Job
from app.jobs.query import (
    JobDateRange,
    JobDetailQuery,
    JobSearchQuery,
    JobSortField,
    SortDirection,
)
from app.jobs.query_service import jobs_query_service
from app.jobs.schemas import (
    JobCancelRequest,
    JobCreateFromAppointmentRequest,
    JobCreateRequest,
    JobDetailResponse,
    JobListItemResponse,
    JobMutationResponse,
    JobPauseRequest,
    JobReopenRequest,
    JobVersionRequest,
    PaginatedJobsResponse,
)
from app.jobs.service import job_service
from app.jobs.types import JobPriority, JobStatus
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import JobPermission
from app.platform.permissions.dependencies import require_permission


router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
JobsReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.READ))
]
JobsManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.MANAGE))
]
JobsExecuteContext = Annotated[
    AuthorizationContext, Depends(require_permission(JobPermission.EXECUTE))
]


def translate_job_error(error: JobError) -> HTTPException:
    if isinstance(error, (JobNotFoundError, JobReferenceNotFoundError)):
        return HTTPException(status_code=404, detail="Job resource was not found.")
    if isinstance(
        error,
        (
            AppointmentAlreadyLinkedError,
            JobInvalidTransitionError,
            JobVersionConflictError,
            JobCompletionBlockedError,
            JobCancellationBlockedError,
            JobReopeningBlockedError,
        ),
    ):
        return HTTPException(
            status_code=409, detail="Job operation conflicts with the current state."
        )
    if isinstance(error, (JobValidationError, JobQueryValidationError)):
        return HTTPException(
            status_code=422, detail="Job request violates domain validation rules."
        )
    return HTTPException(
        status_code=400, detail="Job operation could not be completed."
    )


def _range(
    start: AwareDatetime | None, end: AwareDatetime | None
) -> JobDateRange | None:
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise HTTPException(
            status_code=422, detail="Both date-range boundaries are required."
        )
    return JobDateRange(start_at=start, end_at=end)


def _mutation_response(job: Job) -> JobMutationResponse:
    return JobMutationResponse.model_validate(job)


@router.get("", response_model=PaginatedJobsResponse, summary="Search Jobs")
async def search_jobs(
    context: JobsReadContext,
    session: DatabaseSession,
    branch_id: UUID | None = None,
    status_filter: Annotated[list[JobStatus] | None, Query(alias="status")] = None,
    priority: Annotated[list[JobPriority] | None, Query()] = None,
    job_type: Annotated[list[str] | None, Query()] = None,
    job_number: str | None = None,
    customer_id: UUID | None = None,
    service_location_id: UUID | None = None,
    appointment_id: UUID | None = None,
    created_start_at: AwareDatetime | None = None,
    created_end_at: AwareDatetime | None = None,
    updated_start_at: AwareDatetime | None = None,
    updated_end_at: AwareDatetime | None = None,
    activated_start_at: AwareDatetime | None = None,
    activated_end_at: AwareDatetime | None = None,
    started_start_at: AwareDatetime | None = None,
    started_end_at: AwareDatetime | None = None,
    completed_start_at: AwareDatetime | None = None,
    completed_end_at: AwareDatetime | None = None,
    cancelled_start_at: AwareDatetime | None = None,
    cancelled_end_at: AwareDatetime | None = None,
    has_appointment: bool | None = None,
    has_historical_completion: bool | None = None,
    has_historical_cancellation: bool | None = None,
    search_text: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    sort_field: JobSortField = JobSortField.UPDATED_AT,
    sort_direction: SortDirection = SortDirection.DESC,
) -> PaginatedJobsResponse:
    query = JobSearchQuery(
        branch_id=branch_id,
        statuses=frozenset(status_filter or ()),
        priorities=frozenset(priority or ()),
        job_type_codes=frozenset(job_type or ()),
        job_number=job_number,
        customer_id=customer_id,
        service_location_id=service_location_id,
        appointment_id=appointment_id,
        created_range=_range(created_start_at, created_end_at),
        updated_range=_range(updated_start_at, updated_end_at),
        activated_range=_range(activated_start_at, activated_end_at),
        started_range=_range(started_start_at, started_end_at),
        completed_range=_range(completed_start_at, completed_end_at),
        cancelled_range=_range(cancelled_start_at, cancelled_end_at),
        has_appointment=has_appointment,
        has_historical_completion=has_historical_completion,
        has_historical_cancellation=has_historical_cancellation,
        search_text=search_text,
        page=page,
        page_size=page_size,
        sort_field=sort_field,
        sort_direction=sort_direction,
    )
    try:
        result = await jobs_query_service.search_jobs(
            session, context=context, query=query
        )
    except JobError as error:
        raise translate_job_error(error) from error
    return PaginatedJobsResponse(
        items=tuple(JobListItemResponse.model_validate(item) for item in result.items),
        page=result.page,
        page_size=result.page_size,
        total_count=result.total_count,
        total_pages=result.total_pages,
    )


@router.get("/{job_id}", response_model=JobDetailResponse, summary="Get a Job")
async def get_job(
    job_id: UUID, context: JobsReadContext, session: DatabaseSession
) -> JobDetailResponse:
    try:
        detail = await jobs_query_service.get_job_detail(
            session, context=context, query=JobDetailQuery(job_id)
        )
    except JobError as error:
        raise translate_job_error(error) from error
    return JobDetailResponse.model_validate(detail)


@router.post(
    "",
    response_model=JobMutationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Job",
)
async def create_job(
    data: JobCreateRequest, context: JobsManageContext, session: DatabaseSession
) -> JobMutationResponse:
    try:
        job = await job_service.create_job(
            session, context=context, command=CreateJob(**data.model_dump())
        )
    except JobError as error:
        raise translate_job_error(error) from error
    return _mutation_response(job)


@router.post(
    "/from-appointment",
    response_model=JobMutationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Job from an Appointment",
)
async def create_job_from_appointment(
    data: JobCreateFromAppointmentRequest,
    context: JobsManageContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    try:
        job = await job_service.create_job_from_appointment(
            session,
            context=context,
            command=CreateJobFromAppointment(**data.model_dump()),
        )
    except JobError as error:
        raise translate_job_error(error) from error
    return _mutation_response(job)


async def _version_transition(
    operation: Callable[..., Awaitable[Job]],
    session: AsyncSession,
    context: AuthorizationContext,
    command: object,
) -> JobMutationResponse:
    try:
        job = await operation(session, context=context, command=command)
    except JobError as error:
        raise translate_job_error(error) from error
    return _mutation_response(job)


@router.post(
    "/{job_id}/activate", response_model=JobMutationResponse, summary="Activate a Job"
)
async def activate_job(
    job_id: UUID,
    data: JobVersionRequest,
    context: JobsManageContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.activate_job,
        session,
        context,
        ActivateJob(job_id, data.expected_version),
    )


@router.post(
    "/{job_id}/start", response_model=JobMutationResponse, summary="Start a Job"
)
async def start_job(
    job_id: UUID,
    data: JobVersionRequest,
    context: JobsExecuteContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.start_job, session, context, StartJob(job_id, data.expected_version)
    )


@router.post(
    "/{job_id}/pause", response_model=JobMutationResponse, summary="Pause a Job"
)
async def pause_job(
    job_id: UUID,
    data: JobPauseRequest,
    context: JobsExecuteContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.pause_job,
        session,
        context,
        PauseJob(job_id, data.expected_version, data.reason_code),
    )


@router.post(
    "/{job_id}/resume", response_model=JobMutationResponse, summary="Resume a Job"
)
async def resume_job(
    job_id: UUID,
    data: JobVersionRequest,
    context: JobsExecuteContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.resume_job,
        session,
        context,
        ResumeJob(job_id, data.expected_version),
    )


@router.post(
    "/{job_id}/complete", response_model=JobMutationResponse, summary="Complete a Job"
)
async def complete_job(
    job_id: UUID,
    data: JobVersionRequest,
    context: JobsExecuteContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.complete_job,
        session,
        context,
        CompleteJob(job_id, data.expected_version),
    )


@router.post(
    "/{job_id}/cancel", response_model=JobMutationResponse, summary="Cancel a Job"
)
async def cancel_job(
    job_id: UUID,
    data: JobCancelRequest,
    context: JobsManageContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.cancel_job,
        session,
        context,
        CancelJob(job_id, data.expected_version, data.reason_code),
    )


@router.post(
    "/{job_id}/reopen", response_model=JobMutationResponse, summary="Reopen a Job"
)
async def reopen_job(
    job_id: UUID,
    data: JobReopenRequest,
    context: JobsManageContext,
    session: DatabaseSession,
) -> JobMutationResponse:
    return await _version_transition(
        job_service.reopen_job,
        session,
        context,
        ReopenJob(job_id, data.expected_version, data.reason_code),
    )
