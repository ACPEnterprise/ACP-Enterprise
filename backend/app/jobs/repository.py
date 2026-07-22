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


job_repository = JobRepository()
