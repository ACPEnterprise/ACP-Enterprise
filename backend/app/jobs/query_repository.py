from typing import cast
from uuid import UUID

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.customers.models import Customer, ServiceLocation
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.query import JobQueryScope, JobSearchQuery, JobSortField, SortDirection
from app.jobs.query_types import (
    JobAppointmentSummary,
    JobCustomerSummary,
    JobDetail,
    JobListItem,
    JobServiceLocationSummary,
)
from app.jobs.types import JobCancellationReason, JobPauseReason, JobPriority, JobStatus
from app.scheduling.models import Appointment
from app.scheduling.types import AppointmentStatus


class JobQueryRepository:
    """Own read-only Jobs projection SQL; never locks or mutates records."""

    @staticmethod
    def _base():
        return (
            select(Job)
            .join(
                Customer,
                (Customer.id == Job.customer_id)
                & (Customer.company_id == Job.company_id),
            )
            .join(
                ServiceLocation,
                (ServiceLocation.id == Job.service_location_id)
                & (ServiceLocation.customer_id == Job.customer_id),
            )
        )

    @staticmethod
    def _scope(scope: JobQueryScope) -> list[ColumnElement[bool]]:
        return [
            Job.company_id == scope.company_id,
            Job.branch_id.in_(scope.authorized_branch_ids),
        ]

    @classmethod
    async def get_job_detail_row(
        cls, session: AsyncSession, *, scope: JobQueryScope, job_id: UUID
    ) -> RowMapping | None:
        if not scope.authorized_branch_ids:
            return None
        statement = (
            select(
                *Job.__table__.c,
                Customer.customer_number.label("customer_number"),
                Customer.display_name.label("customer_display_name"),
                ServiceLocation.nickname.label("location_nickname"),
                ServiceLocation.address.label("location_address"),
                ServiceLocation.address_line_2.label("location_address_line_2"),
                ServiceLocation.city.label("location_city"),
                ServiceLocation.state.label("location_state"),
                ServiceLocation.postal_code.label("location_postal_code"),
                ServiceLocation.country.label("location_country"),
            )
            .select_from(Job)
            .join(
                Customer,
                (Customer.id == Job.customer_id)
                & (Customer.company_id == Job.company_id),
            )
            .join(
                ServiceLocation,
                (ServiceLocation.id == Job.service_location_id)
                & (ServiceLocation.customer_id == Job.customer_id),
            )
            .where(*cls._scope(scope), Job.id == job_id)
        )
        return (await session.execute(statement)).mappings().one_or_none()

    @staticmethod
    async def get_job_appointment_summaries(
        session: AsyncSession, *, scope: JobQueryScope, job_id: UUID
    ) -> tuple[JobAppointmentSummary, ...]:
        rows = (
            (
                await session.execute(
                    select(
                        JobAppointmentLink.appointment_id,
                        JobAppointmentLink.visit_sequence,
                        Appointment.appointment_number,
                        Appointment.status,
                        Appointment.arrival_window_start_at,
                        Appointment.arrival_window_end_at,
                        Appointment.expected_duration_minutes,
                    )
                    .join(
                        Appointment,
                        (Appointment.id == JobAppointmentLink.appointment_id)
                        & (Appointment.company_id == JobAppointmentLink.company_id)
                        & (Appointment.branch_id == JobAppointmentLink.branch_id),
                    )
                    .where(
                        JobAppointmentLink.company_id == scope.company_id,
                        JobAppointmentLink.branch_id.in_(scope.authorized_branch_ids),
                        JobAppointmentLink.job_id == job_id,
                    )
                    .order_by(
                        JobAppointmentLink.visit_sequence,
                        JobAppointmentLink.appointment_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        return tuple(
            JobAppointmentSummary(
                appointment_id=row["appointment_id"],
                visit_sequence=row["visit_sequence"],
                appointment_number=row["appointment_number"],
                status=AppointmentStatus(row["status"]),
                arrival_window_start_at=row["arrival_window_start_at"],
                arrival_window_end_at=row["arrival_window_end_at"],
                expected_duration_minutes=row["expected_duration_minutes"],
            )
            for row in rows
        )

    @classmethod
    def detail(
        cls, row: RowMapping, appointments: tuple[JobAppointmentSummary, ...]
    ) -> JobDetail:
        return JobDetail(
            id=row["id"],
            job_number=row["job_number"],
            company_id=row["company_id"],
            branch_id=row["branch_id"],
            customer_id=row["customer_id"],
            service_location_id=row["service_location_id"],
            status=JobStatus(row["status"]),
            concurrency_version=row["concurrency_version"],
            activated_at=row["activated_at"],
            started_at=row["started_at"],
            paused_at=row["paused_at"],
            pause_reason_code=JobPauseReason(row["pause_reason_code"])
            if row["pause_reason_code"]
            else None,
            completed_at=row["completed_at"],
            completed_by_user_id=row["completed_by_user_id"],
            cancelled_at=row["cancelled_at"],
            cancelled_by_user_id=row["cancelled_by_user_id"],
            cancellation_reason_code=JobCancellationReason(
                row["cancellation_reason_code"]
            )
            if row["cancellation_reason_code"]
            else None,
            created_at=row["created_at"],
            created_by_user_id=row["created_by_user_id"],
            updated_at=row["updated_at"],
            updated_by_user_id=row["updated_by_user_id"],
            job_type_code=row["job_type_code"],
            priority=JobPriority(row["priority"]),
            customer_reported_problem=row["customer_reported_problem"],
            internal_description=row["internal_description"],
            customer=JobCustomerSummary(
                row["customer_id"], row["customer_number"], row["customer_display_name"]
            ),
            service_location=JobServiceLocationSummary(
                row["service_location_id"],
                row["location_nickname"],
                row["location_address"],
                row["location_address_line_2"],
                row["location_city"],
                row["location_state"],
                row["location_postal_code"],
                row["location_country"],
            ),
            appointments=appointments,
        )

    @classmethod
    def _filters(
        cls, scope: JobQueryScope, query: JobSearchQuery
    ) -> list[ColumnElement[bool]]:
        filters = cls._scope(scope)
        if query.branch_id:
            filters.append(Job.branch_id == query.branch_id)
        if query.statuses:
            filters.append(Job.status.in_(s.value for s in query.statuses))
        if query.priorities:
            filters.append(Job.priority.in_(p.value for p in query.priorities))
        if query.job_type_codes:
            filters.append(Job.job_type_code.in_(query.job_type_codes))
        if query.job_number:
            filters.append(Job.job_number == query.job_number)
        if query.customer_id:
            filters.append(Job.customer_id == query.customer_id)
        if query.service_location_id:
            filters.append(Job.service_location_id == query.service_location_id)
        link_exists = exists(
            select(1).where(
                JobAppointmentLink.job_id == Job.id,
                JobAppointmentLink.company_id == Job.company_id,
            )
        )
        if query.appointment_id:
            filters.append(
                exists(
                    select(1).where(
                        JobAppointmentLink.job_id == Job.id,
                        JobAppointmentLink.company_id == Job.company_id,
                        JobAppointmentLink.appointment_id == query.appointment_id,
                    )
                )
            )
        if query.has_appointment is not None:
            filters.append(link_exists if query.has_appointment else ~link_exists)
        if query.has_historical_completion is not None:
            filters.append(
                Job.completed_at.is_not(None)
                if query.has_historical_completion
                else Job.completed_at.is_(None)
            )
        if query.has_historical_cancellation is not None:
            filters.append(
                Job.cancelled_at.is_not(None)
                if query.has_historical_cancellation
                else Job.cancelled_at.is_(None)
            )
        for field, value in (
            (Job.created_at, query.created_range),
            (Job.updated_at, query.updated_range),
            (Job.activated_at, query.activated_range),
            (Job.started_at, query.started_range),
            (Job.completed_at, query.completed_range),
            (Job.cancelled_at, query.cancelled_range),
        ):
            if value:
                filters.extend((field >= value.start_at, field < value.end_at))
        if query.search_text:
            pattern = f"%{query.search_text}%"
            appointment_match = exists(
                select(1)
                .select_from(JobAppointmentLink)
                .join(Appointment, Appointment.id == JobAppointmentLink.appointment_id)
                .where(
                    JobAppointmentLink.job_id == Job.id,
                    JobAppointmentLink.company_id == Job.company_id,
                    Appointment.appointment_number.ilike(pattern),
                )
            )
            filters.append(
                or_(
                    Job.job_number.ilike(pattern),
                    Customer.display_name.ilike(pattern),
                    Customer.legal_name.ilike(pattern),
                    ServiceLocation.address.ilike(pattern),
                    ServiceLocation.city.ilike(pattern),
                    ServiceLocation.postal_code.ilike(pattern),
                    Job.customer_reported_problem.ilike(pattern),
                    appointment_match,
                )
            )
        return filters

    @classmethod
    async def count_jobs(
        cls, session: AsyncSession, *, scope: JobQueryScope, query: JobSearchQuery
    ) -> int:
        if not scope.authorized_branch_ids:
            return 0
        value = cast(
            int | None,
            await session.scalar(
                select(func.count())
                .select_from(Job)
                .join(
                    Customer,
                    (Customer.id == Job.customer_id)
                    & (Customer.company_id == Job.company_id),
                )
                .join(
                    ServiceLocation,
                    (ServiceLocation.id == Job.service_location_id)
                    & (ServiceLocation.customer_id == Job.customer_id),
                )
                .where(*cls._filters(scope, query))
            ),
        )
        return int(value or 0)

    @classmethod
    async def search_jobs(
        cls, session: AsyncSession, *, scope: JobQueryScope, query: JobSearchQuery
    ) -> tuple[JobListItem, ...]:
        if not scope.authorized_branch_ids:
            return ()
        appointment_count = (
            select(func.count())
            .select_from(JobAppointmentLink)
            .where(
                JobAppointmentLink.job_id == Job.id,
                JobAppointmentLink.company_id == Job.company_id,
            )
            .correlate(Job)
            .scalar_subquery()
        )
        earliest = (
            select(func.min(Appointment.arrival_window_start_at))
            .select_from(JobAppointmentLink)
            .join(Appointment, Appointment.id == JobAppointmentLink.appointment_id)
            .where(
                JobAppointmentLink.job_id == Job.id,
                JobAppointmentLink.company_id == Job.company_id,
            )
            .correlate(Job)
            .scalar_subquery()
        )
        label = func.concat_ws(
            ", ",
            func.coalesce(ServiceLocation.nickname, ServiceLocation.address),
            ServiceLocation.city,
            ServiceLocation.state,
            ServiceLocation.postal_code,
        )
        statement = (
            select(
                Job.id,
                Job.job_number,
                Job.branch_id,
                Job.customer_id,
                Customer.display_name.label("customer_display_name"),
                Job.service_location_id,
                label.label("service_location_label"),
                Job.status,
                Job.priority,
                Job.job_type_code,
                func.left(Job.customer_reported_problem, 160).label("problem_summary"),
                appointment_count.label("appointment_count"),
                earliest.label("earliest_appointment_start_at"),
                Job.created_at,
                Job.updated_at,
                Job.started_at,
                Job.completed_at,
                Job.concurrency_version,
            )
            .select_from(Job)
            .join(
                Customer,
                (Customer.id == Job.customer_id)
                & (Customer.company_id == Job.company_id),
            )
            .join(
                ServiceLocation,
                (ServiceLocation.id == Job.service_location_id)
                & (ServiceLocation.customer_id == Job.customer_id),
            )
            .where(*cls._filters(scope, query))
        )
        priority = case(
            {"low": 10, "normal": 20, "high": 30, "urgent": 40, "emergency": 50},
            value=Job.priority,
        )
        status = case(
            {
                "draft": 10,
                "ready": 20,
                "in_progress": 30,
                "paused": 40,
                "completed": 50,
                "cancelled": 60,
            },
            value=Job.status,
        )
        sorts = {
            JobSortField.JOB_NUMBER: Job.job_number,
            JobSortField.PRIORITY: priority,
            JobSortField.STATUS: status,
            JobSortField.CREATED_AT: Job.created_at,
            JobSortField.UPDATED_AT: Job.updated_at,
            JobSortField.ACTIVATED_AT: Job.activated_at,
            JobSortField.STARTED_AT: Job.started_at,
            JobSortField.COMPLETED_AT: Job.completed_at,
            JobSortField.CANCELLED_AT: Job.cancelled_at,
            JobSortField.CUSTOMER_DISPLAY_NAME: func.lower(Customer.display_name),
            JobSortField.EARLIEST_APPOINTMENT_START_AT: earliest,
        }
        expression = sorts[query.sort_field]
        ordered = (
            expression.asc().nulls_last()
            if query.sort_direction is SortDirection.ASC
            else expression.desc().nulls_last()
        )
        rows = (
            (
                await session.execute(
                    statement.order_by(ordered, Job.id.asc())
                    .limit(query.page_size)
                    .offset((query.page - 1) * query.page_size)
                )
            )
            .mappings()
            .all()
        )
        return tuple(
            JobListItem(
                id=r["id"],
                job_number=r["job_number"],
                branch_id=r["branch_id"],
                customer_id=r["customer_id"],
                customer_display_name=r["customer_display_name"],
                service_location_id=r["service_location_id"],
                service_location_label=r["service_location_label"],
                status=JobStatus(r["status"]),
                priority=JobPriority(r["priority"]),
                job_type_code=r["job_type_code"],
                customer_reported_problem_summary=r["problem_summary"],
                appointment_count=int(r["appointment_count"]),
                earliest_appointment_start_at=r["earliest_appointment_start_at"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                concurrency_version=r["concurrency_version"],
            )
            for r in rows
        )


job_query_repository = JobQueryRepository()
