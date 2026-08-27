from datetime import date, datetime, time, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import (
    DispatchAssignment,
    DispatchAssignmentHistory,
    DispatchCrewMember,
)
from app.field_service.errors import (
    FieldServiceConflict,
    FieldServiceNotFound,
    FieldServiceValidation,
)
from app.field_service.models import (
    FieldCustomerApproval,
    FieldInvoiceHandoff,
    FieldWorkNote,
)
from app.field_service.schemas import (
    ApprovalInput,
    FieldJobState,
    HandoffInput,
    Itinerary,
    ItineraryItem,
    NoteInput,
)
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment


class FieldService:
    async def itinerary(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        service_date: date,
    ) -> Itinerary:
        employee = await self._employee(session, context)
        start = datetime.combine(service_date, time.min, tzinfo=timezone.utc)
        end = datetime.combine(service_date, time.max, tzinfo=timezone.utc)
        crew_assignment_ids = select(DispatchCrewMember.assignment_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.employee_id == employee.id,
            DispatchCrewMember.status == "active",
        )
        assignments = tuple(
            (
                await session.scalars(
                    select(DispatchAssignment)
                    .where(
                        DispatchAssignment.company_id == context.company.id,
                        DispatchAssignment.branch_id.in_(context.authorized_branch_ids),
                        DispatchAssignment.window_start_at <= end,
                        DispatchAssignment.window_end_at >= start,
                        DispatchAssignment.status.in_(
                            ("assigned", "acknowledged", "reconciliation_required")
                        ),
                        or_(
                            DispatchAssignment.primary_employee_id == employee.id,
                            DispatchAssignment.id.in_(crew_assignment_ids),
                        ),
                    )
                    .order_by(DispatchAssignment.window_start_at, DispatchAssignment.id)
                )
            ).all()
        )
        items: list[ItineraryItem] = []
        for assignment in assignments:
            appointment = await session.scalar(
                select(Appointment).where(
                    Appointment.company_id == context.company.id,
                    Appointment.id == assignment.appointment_id,
                )
            )
            if (
                appointment is None
                or appointment.arrival_window_start_at is None
                or appointment.arrival_window_end_at is None
            ):
                continue
            customer = await session.scalar(
                select(Customer).where(
                    Customer.company_id == context.company.id,
                    Customer.id == appointment.customer_id,
                )
            )
            location = await session.scalar(
                select(ServiceLocation).where(
                    ServiceLocation.id == appointment.service_location_id,
                    ServiceLocation.customer_id == appointment.customer_id,
                )
            )
            job = (
                await session.scalar(
                    select(Job).where(
                        Job.company_id == context.company.id,
                        Job.id == assignment.job_id,
                    )
                )
                if assignment.job_id
                else None
            )
            arrival = await self._arrival(session, context.company.id, assignment.id)
            items.append(
                ItineraryItem(
                    appointment_id=appointment.id,
                    appointment_number=appointment.appointment_number,
                    job_id=job.id if job else None,
                    job_number=job.job_number if job else None,
                    job_status=job.status if job else None,
                    job_version=job.concurrency_version if job else None,
                    customer_display_name=customer.display_name
                    if customer
                    else "Customer unavailable",
                    service_location_label=self._location_label(location),
                    window_start_at=appointment.arrival_window_start_at,
                    window_end_at=appointment.arrival_window_end_at,
                    assignment_status=assignment.status,
                    assignment_version=assignment.version,
                    arrival_state=arrival,
                )
            )
        return Itinerary(
            service_date=service_date,
            technician_display_name=employee.display_name,
            items=tuple(items),
        )

    async def state(
        self, session: AsyncSession, *, context: AuthorizationContext, job_id: UUID
    ) -> FieldJobState:
        assignment = await self._assigned_job(session, context, job_id)
        summary = await session.scalar(
            select(FieldWorkNote.id)
            .where(
                FieldWorkNote.company_id == context.company.id,
                FieldWorkNote.job_id == job_id,
                FieldWorkNote.note_type == "work_performed",
            )
            .limit(1)
        )
        approval = await session.scalar(
            select(FieldCustomerApproval)
            .where(
                FieldCustomerApproval.company_id == context.company.id,
                FieldCustomerApproval.job_id == job_id,
            )
            .order_by(FieldCustomerApproval.created_at.desc())
            .limit(1)
        )
        handoff = await session.scalar(
            select(FieldInvoiceHandoff).where(
                FieldInvoiceHandoff.company_id == context.company.id,
                FieldInvoiceHandoff.job_id == job_id,
            )
        )
        return FieldJobState(
            job_id=job_id,
            assignment_id=assignment.id,
            work_summary_recorded=summary is not None,
            customer_disposition=approval.disposition if approval else None,
            completion_ready=summary is not None
            and approval is not None
            and assignment.status != "reconciliation_required",
            invoice_handoff_status=handoff.status if handoff else None,
            invoice_id=handoff.invoice_id if handoff else None,
        )

    async def note(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: NoteInput,
    ) -> FieldJobState:
        async with session.begin():
            assignment = await self._assigned_job(session, context, job_id)
            prior = await session.scalar(
                select(FieldWorkNote).where(
                    FieldWorkNote.company_id == context.company.id,
                    FieldWorkNote.idempotency_key == payload.idempotency_key,
                )
            )
            if prior is None:
                session.add(
                    FieldWorkNote(
                        company_id=context.company.id,
                        branch_id=assignment.branch_id,
                        job_id=job_id,
                        assignment_id=assignment.id,
                        note_type=payload.note_type,
                        content=payload.content.strip(),
                        idempotency_key=payload.idempotency_key,
                        recorded_by_user_id=context.user.id,
                    )
                )
        return await self.state(session, context=context, job_id=job_id)

    async def approval(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: ApprovalInput,
    ) -> FieldJobState:
        if (
            payload.disposition == "approved"
            and not (payload.customer_name or "").strip()
        ):
            raise FieldServiceValidation("Customer name is required for approval.")
        if payload.disposition != "approved" and not (payload.reason or "").strip():
            raise FieldServiceValidation(
                "A reason is required when approval is unavailable or refused."
            )
        async with session.begin():
            assignment = await self._assigned_job(session, context, job_id)
            prior = await session.scalar(
                select(FieldCustomerApproval).where(
                    FieldCustomerApproval.company_id == context.company.id,
                    FieldCustomerApproval.idempotency_key == payload.idempotency_key,
                )
            )
            if prior is None:
                session.add(
                    FieldCustomerApproval(
                        company_id=context.company.id,
                        branch_id=assignment.branch_id,
                        job_id=job_id,
                        assignment_id=assignment.id,
                        disposition=payload.disposition,
                        customer_name=(payload.customer_name or "").strip() or None,
                        reason=(payload.reason or "").strip() or None,
                        idempotency_key=payload.idempotency_key,
                        recorded_by_user_id=context.user.id,
                    )
                )
        return await self.state(session, context=context, job_id=job_id)

    async def refresh_handoff(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: HandoffInput,
    ) -> FieldJobState:
        async with session.begin():
            assignment = await self._assigned_job(session, context, job_id)
            job = await session.scalar(
                select(Job).where(
                    Job.company_id == context.company.id, Job.id == job_id
                )
            )
            if job is None or job.status != "completed":
                raise FieldServiceConflict(
                    "Job completion is required before invoice handoff."
                )
            invoice = await session.scalar(
                select(Invoice)
                .where(
                    Invoice.company_id == context.company.id,
                    Invoice.branch_id == assignment.branch_id,
                    Invoice.job_id == job_id,
                )
                .order_by(Invoice.created_at.desc())
                .limit(1)
            )
            handoff = await session.scalar(
                select(FieldInvoiceHandoff)
                .where(
                    FieldInvoiceHandoff.company_id == context.company.id,
                    FieldInvoiceHandoff.job_id == job_id,
                )
                .with_for_update()
            )
            status = "completed" if invoice else "pending"
            if handoff is None:
                session.add(
                    FieldInvoiceHandoff(
                        company_id=context.company.id,
                        branch_id=assignment.branch_id,
                        job_id=job_id,
                        assignment_id=assignment.id,
                        invoice_id=invoice.id if invoice else None,
                        status=status,
                        idempotency_key=payload.idempotency_key,
                        requested_by_user_id=context.user.id,
                    )
                )
            else:
                handoff.invoice_id = invoice.id if invoice else None
                handoff.status = status
                handoff.updated_at = datetime.now(timezone.utc)
        return await self.state(session, context=context, job_id=job_id)

    async def _assigned_job(
        self, session: AsyncSession, context: AuthorizationContext, job_id: UUID
    ) -> DispatchAssignment:
        employee = await self._employee(session, context)
        crew = select(DispatchCrewMember.assignment_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.employee_id == employee.id,
            DispatchCrewMember.status == "active",
        )
        assignment = await session.scalar(
            select(DispatchAssignment)
            .where(
                DispatchAssignment.company_id == context.company.id,
                DispatchAssignment.branch_id.in_(context.authorized_branch_ids),
                DispatchAssignment.job_id == job_id,
                DispatchAssignment.status.in_(
                    ("assigned", "acknowledged", "reconciliation_required")
                ),
                or_(
                    DispatchAssignment.primary_employee_id == employee.id,
                    DispatchAssignment.id.in_(crew),
                ),
            )
            .limit(1)
        )
        if assignment is None:
            raise FieldServiceNotFound("Assigned field Job was not found.")
        return assignment

    @staticmethod
    async def _employee(
        session: AsyncSession, context: AuthorizationContext
    ) -> Employee:
        employee = await session.scalar(
            select(Employee)
            .where(
                Employee.company_id == context.company.id,
                Employee.membership_id == context.membership.id,
                Employee.status == "active",
                Employee.archived_at.is_(None),
            )
            .limit(1)
        )
        if employee is None:
            raise FieldServiceNotFound("Active technician identity was not found.")
        return employee

    @staticmethod
    async def _arrival(
        session: AsyncSession, company_id: UUID, assignment_id: UUID
    ) -> str:
        events = tuple(
            (
                await session.scalars(
                    select(DispatchAssignmentHistory.event_type)
                    .where(
                        DispatchAssignmentHistory.company_id == company_id,
                        DispatchAssignmentHistory.assignment_id == assignment_id,
                        DispatchAssignmentHistory.event_type.in_(
                            ("technician_en_route", "technician_arrived")
                        ),
                    )
                    .order_by(DispatchAssignmentHistory.occurred_at)
                )
            ).all()
        )
        return (
            "arrived"
            if "technician_arrived" in events
            else ("en_route" if "technician_en_route" in events else "pending")
        )

    @staticmethod
    def _location_label(location: ServiceLocation | None) -> str:
        if location is None:
            return "Service location unavailable"
        return ", ".join(
            part
            for part in (
                location.nickname or location.address,
                location.city,
                location.state,
            )
            if part
        )


field_service = FieldService()
