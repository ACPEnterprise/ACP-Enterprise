import re
from dataclasses import replace
from math import ceil

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.errors import JobNotFoundError, JobQueryValidationError
from app.jobs.query import JobDateRange, JobDetailQuery, JobQueryScope, JobSearchQuery
from app.jobs.query_repository import JobQueryRepository, job_query_repository
from app.jobs.query_types import JobDetail, PaginatedJobs
from app.platform.permissions.authorization import AuthorizationContext


MAX_SEARCH_LENGTH = 200
TYPE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
JOB_NUMBER = re.compile(r"^JOB-[0-9]{6,}$")


class JobsQueryService:
    def __init__(self, repository: JobQueryRepository = job_query_repository) -> None:
        self._repository = repository

    async def get_job_detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: JobDetailQuery,
    ) -> JobDetail:
        scope = self._scope(context)
        row = await self._repository.get_job_detail_row(
            session, scope=scope, job_id=query.job_id
        )
        if row is None:
            raise JobNotFoundError(query.job_id)
        appointments = await self._repository.get_job_appointment_summaries(
            session, scope=scope, job_id=query.job_id
        )
        return self._repository.detail(row, appointments)

    async def search_jobs(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: JobSearchQuery,
    ) -> PaginatedJobs:
        scope = self._scope(context)
        normalized = self._validate(context, query)
        total = await self._repository.count_jobs(
            session, scope=scope, query=normalized
        )
        items = await self._repository.search_jobs(
            session, scope=scope, query=normalized
        )
        return PaginatedJobs(
            items=items,
            page=normalized.page,
            page_size=normalized.page_size,
            total_count=total,
            total_pages=ceil(total / normalized.page_size) if total else 0,
        )

    @staticmethod
    def _scope(context: AuthorizationContext) -> JobQueryScope:
        return JobQueryScope(
            company_id=context.company.id,
            authorized_branch_ids=context.authorized_branch_ids,
        )

    @staticmethod
    def _validate(
        context: AuthorizationContext, query: JobSearchQuery
    ) -> JobSearchQuery:
        if query.branch_id is not None and not context.can_access_branch(
            query.branch_id
        ):
            raise JobNotFoundError(query.branch_id)
        if query.page < 1 or not 1 <= query.page_size <= 200:
            raise JobQueryValidationError("Query pagination is invalid.")
        for value in (
            query.created_range,
            query.updated_range,
            query.activated_range,
            query.started_range,
            query.completed_range,
            query.cancelled_range,
        ):
            JobsQueryService._validate_range(value)
        job_type_codes = frozenset(
            code.strip().lower() for code in query.job_type_codes
        )
        for code in job_type_codes:
            if not TYPE_CODE.fullmatch(code):
                raise JobQueryValidationError("Job type code is invalid.")
        job_number = query.job_number.strip().upper() if query.job_number else None
        if job_number is not None and not JOB_NUMBER.fullmatch(job_number):
            raise JobQueryValidationError("Job number is invalid.")
        search = query.search_text.strip() if query.search_text is not None else None
        if search is not None and (not search or len(search) > MAX_SEARCH_LENGTH):
            raise JobQueryValidationError("Search text is invalid.")
        return replace(
            query,
            job_type_codes=job_type_codes,
            job_number=job_number,
            search_text=search,
        )

    @staticmethod
    def _validate_range(value: JobDateRange | None) -> None:
        if value is None:
            return
        if value.start_at.tzinfo is None or value.end_at.tzinfo is None:
            raise JobQueryValidationError("Date ranges must be timezone-aware.")
        if value.end_at <= value.start_at:
            raise JobQueryValidationError("Date range end must follow start.")


jobs_query_service = JobsQueryService()
