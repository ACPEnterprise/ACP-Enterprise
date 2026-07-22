from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import Job, JobAppointmentLink, JobNumberSequence


class JobRepository:
    """Own Jobs persistence and locking without transactions or policy decisions."""

    @staticmethod
    async def next_job_number(session: AsyncSession, *, company_id: UUID) -> str:
        statement = (
            insert(JobNumberSequence)
            .values(company_id=company_id, last_value=1)
            .on_conflict_do_update(
                index_elements=[JobNumberSequence.company_id],
                set_={
                    "last_value": JobNumberSequence.last_value + 1,
                    "updated_at": func.now(),
                },
            )
            .returning(JobNumberSequence.last_value)
        )
        value = await session.scalar(statement)
        if value is None:
            raise RuntimeError("Job number allocation failed")
        return f"JOB-{value:06d}"

    @staticmethod
    async def create_job(session: AsyncSession, *, job: Job) -> Job:
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get_job(
        session: AsyncSession, *, company_id: UUID, job_id: UUID
    ) -> Job | None:
        return await session.scalar(
            select(Job).where(Job.company_id == company_id, Job.id == job_id)
        )

    @staticmethod
    async def get_job_by_number(
        session: AsyncSession, *, company_id: UUID, job_number: str
    ) -> Job | None:
        return await session.scalar(
            select(Job).where(
                Job.company_id == company_id, Job.job_number == job_number
            )
        )

    @staticmethod
    async def get_job_for_update(
        session: AsyncSession, *, company_id: UUID, job_id: UUID
    ) -> Job | None:
        return await session.scalar(
            select(Job)
            .where(Job.company_id == company_id, Job.id == job_id)
            .with_for_update()
        )

    @staticmethod
    async def create_appointment_link(
        session: AsyncSession, *, link: JobAppointmentLink
    ) -> JobAppointmentLink:
        session.add(link)
        await session.flush()
        return link

    @staticmethod
    async def list_appointment_links(
        session: AsyncSession, *, company_id: UUID, job_id: UUID
    ) -> tuple[JobAppointmentLink, ...]:
        records = await session.scalars(
            select(JobAppointmentLink)
            .where(
                JobAppointmentLink.company_id == company_id,
                JobAppointmentLink.job_id == job_id,
            )
            .order_by(JobAppointmentLink.visit_sequence, JobAppointmentLink.id)
        )
        return tuple(records.all())

    @staticmethod
    async def get_links_for_appointment(
        session: AsyncSession, *, company_id: UUID, appointment_id: UUID
    ) -> tuple[JobAppointmentLink, ...]:
        records = await session.scalars(
            select(JobAppointmentLink)
            .where(
                JobAppointmentLink.company_id == company_id,
                JobAppointmentLink.appointment_id == appointment_id,
            )
            .order_by(JobAppointmentLink.job_id, JobAppointmentLink.id)
        )
        return tuple(records.all())

    @staticmethod
    async def has_appointment_links(
        session: AsyncSession, *, company_id: UUID, job_id: UUID
    ) -> bool:
        return bool(
            await session.scalar(
                select(
                    select(JobAppointmentLink.id)
                    .where(
                        JobAppointmentLink.company_id == company_id,
                        JobAppointmentLink.job_id == job_id,
                    )
                    .exists()
                )
            )
        )

    @staticmethod
    def update_job_metadata(
        job: Job,
        *,
        changes: dict[str, object],
        actor_user_id: UUID,
        updated_at: datetime,
    ) -> tuple[str, ...]:
        allowed = {
            "customer_id",
            "service_location_id",
            "job_type_code",
            "priority",
            "customer_reported_problem",
            "internal_description",
        }
        unexpected = changes.keys() - allowed
        if unexpected:
            raise ValueError(f"Unsupported Job metadata fields: {sorted(unexpected)}")
        changed: list[str] = []
        for field, value in changes.items():
            if getattr(job, field) != value:
                setattr(job, field, value)
                changed.append(field)
        if changed:
            JobRepository._touch(
                job, actor_user_id=actor_user_id, updated_at=updated_at
            )
        return tuple(sorted(changed))

    @staticmethod
    def activate_job(job: Job, *, actor_user_id: UUID, occurred_at: datetime) -> None:
        job.status = "ready"
        job.activated_at = occurred_at
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def start_job(job: Job, *, actor_user_id: UUID, occurred_at: datetime) -> None:
        job.status = "in_progress"
        job.started_at = occurred_at
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def pause_job(
        job: Job,
        *,
        reason_code: str,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> None:
        job.status = "paused"
        job.paused_at = occurred_at
        job.pause_reason_code = reason_code
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def resume_job(job: Job, *, actor_user_id: UUID, occurred_at: datetime) -> None:
        job.status = "in_progress"
        job.paused_at = None
        job.pause_reason_code = None
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def complete_job(job: Job, *, actor_user_id: UUID, occurred_at: datetime) -> None:
        job.status = "completed"
        job.completed_at = occurred_at
        job.completed_by_user_id = actor_user_id
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def cancel_job(
        job: Job,
        *,
        reason_code: str,
        actor_user_id: UUID,
        occurred_at: datetime,
    ) -> None:
        job.status = "cancelled"
        job.cancelled_at = occurred_at
        job.cancelled_by_user_id = actor_user_id
        job.cancellation_reason_code = reason_code
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def reopen_job(job: Job, *, actor_user_id: UUID, occurred_at: datetime) -> None:
        job.status = "ready"
        job.activated_at = job.activated_at or occurred_at
        job.paused_at = None
        job.pause_reason_code = None
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def mark_appointment_linked(
        job: Job, *, actor_user_id: UUID, occurred_at: datetime
    ) -> None:
        JobRepository._touch(job, actor_user_id=actor_user_id, updated_at=occurred_at)

    @staticmethod
    def _touch(job: Job, *, actor_user_id: UUID, updated_at: datetime) -> None:
        job.updated_by_user_id = actor_user_id
        job.updated_at = updated_at
        job.concurrency_version += 1


job_repository = JobRepository()
