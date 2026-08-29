from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import Select, case, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import DispatchAssignment, DispatchCrewMember
from app.jobs.models import Job
from app.platform.employees.models import Employee
from app.scheduling.models import Appointment

ACTIVE_ASSIGNMENT_STATUSES = ("assigned", "acknowledged", "reconciliation_required")


@dataclass(frozen=True)
class EmployeeDayRecord:
    appointment_id: UUID
    appointment_number: str
    appointment_status: str
    job_id: UUID | None
    job_number: str | None
    job_status: str | None
    service_category: str | None
    window_start_at: datetime
    window_end_at: datetime
    assignment_role: Literal["primary", "crew"]
    assignment_status: str
    customer_display_name: str
    location_nickname: str | None
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str


class EmployeeDayRepository:
    async def employee_for_membership(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        membership_id: UUID,
    ) -> Employee | None:
        return await session.scalar(
            select(Employee).where(
                Employee.company_id == company_id,
                Employee.membership_id == membership_id,
                Employee.status == "active",
                Employee.archived_at.is_(None),
            )
        )

    @staticmethod
    def day_statement(
        *,
        company_id: UUID,
        employee_id: UUID,
        authorized_branch_ids: frozenset[UUID],
        start_at: datetime,
        end_at: datetime,
    ) -> Select[tuple[object, ...]]:
        active_crew = exists(
            select(DispatchCrewMember.id).where(
                DispatchCrewMember.company_id == company_id,
                DispatchCrewMember.assignment_id == DispatchAssignment.id,
                DispatchCrewMember.employee_id == employee_id,
                DispatchCrewMember.status == "active",
            )
        )
        role = case(
            (DispatchAssignment.primary_employee_id == employee_id, "primary"),
            else_="crew",
        ).label("assignment_role")
        return (
            select(
                Appointment.id.label("appointment_id"),
                Appointment.appointment_number,
                Appointment.status.label("appointment_status"),
                Job.id.label("job_id"),
                Job.job_number,
                Job.status.label("job_status"),
                Job.job_type_code.label("service_category"),
                Appointment.arrival_window_start_at.label("window_start_at"),
                Appointment.arrival_window_end_at.label("window_end_at"),
                role,
                DispatchAssignment.status.label("assignment_status"),
                Customer.display_name.label("customer_display_name"),
                ServiceLocation.nickname.label("location_nickname"),
                ServiceLocation.address.label("address_line_1"),
                ServiceLocation.address_line_2,
                ServiceLocation.city,
                ServiceLocation.state,
                ServiceLocation.postal_code,
                ServiceLocation.country,
            )
            .select_from(DispatchAssignment)
            .join(
                Appointment,
                (Appointment.company_id == DispatchAssignment.company_id)
                & (Appointment.branch_id == DispatchAssignment.branch_id)
                & (Appointment.id == DispatchAssignment.appointment_id),
            )
            .join(
                Customer,
                (Customer.company_id == Appointment.company_id)
                & (Customer.id == Appointment.customer_id),
            )
            .join(
                ServiceLocation,
                (ServiceLocation.id == Appointment.service_location_id)
                & (ServiceLocation.customer_id == Appointment.customer_id),
            )
            .outerjoin(
                Job,
                (Job.company_id == DispatchAssignment.company_id)
                & (Job.branch_id == DispatchAssignment.branch_id)
                & (Job.id == DispatchAssignment.job_id),
            )
            .where(
                DispatchAssignment.company_id == company_id,
                DispatchAssignment.branch_id.in_(authorized_branch_ids),
                DispatchAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
                Appointment.arrival_window_start_at.is_not(None),
                Appointment.arrival_window_end_at.is_not(None),
                Appointment.arrival_window_start_at < end_at,
                Appointment.arrival_window_end_at > start_at,
                or_(
                    DispatchAssignment.primary_employee_id == employee_id,
                    active_crew,
                ),
            )
            .order_by(Appointment.arrival_window_start_at, Appointment.id)
        )

    async def assignments_for_day(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        authorized_branch_ids: frozenset[UUID],
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[EmployeeDayRecord, ...]:
        if not authorized_branch_ids:
            return ()
        rows = (
            await session.execute(
                self.day_statement(
                    company_id=company_id,
                    employee_id=employee_id,
                    authorized_branch_ids=authorized_branch_ids,
                    start_at=start_at,
                    end_at=end_at,
                )
            )
        ).mappings()
        return tuple(EmployeeDayRecord(**row) for row in rows)


employee_day_repository = EmployeeDayRepository()
