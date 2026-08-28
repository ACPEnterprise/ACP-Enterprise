import hashlib
import json
from datetime import date, datetime, time, timezone
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import (
    DispatchAssignment,
    DispatchAssignmentHistory,
    DispatchCrewMember,
)
from app.estimates.models import Estimate, EstimateJobConversion
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.field_service.errors import (
    FieldServiceConflict,
    FieldServiceNotFound,
    FieldServiceValidation,
)
from app.field_service.models import (
    FieldCompletionEvidence,
    FieldCompletionRequirementSnapshot,
    FieldCustomerApproval,
    FieldInvoiceHandoff,
    FieldNonBillableDisposition,
    FieldWorkNote,
)
from app.field_service.schemas import (
    ApprovalInput,
    FieldJobState,
    HandoffInput,
    Itinerary,
    ItineraryItem,
    NonBillableInput,
    NoteInput,
)
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment


class FieldService:
    COMPLETION_REQUIREMENTS = (
        "work_performed_summary",
        "customer_disposition",
        "commercial_authorization",
    )

    async def itinerary(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        service_date: date,
    ) -> Itinerary:
        employee = await self._employee(session, context)
        start, end = self._service_day_bounds(service_date, context.company.timezone)
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
        snapshot = await session.scalar(
            select(FieldCompletionRequirementSnapshot).where(
                FieldCompletionRequirementSnapshot.company_id == context.company.id,
                FieldCompletionRequirementSnapshot.job_id == job_id,
            )
        )
        evidence_codes = set(
            (
                await session.scalars(
                    select(FieldCompletionEvidence.requirement_code).where(
                        FieldCompletionEvidence.company_id == context.company.id,
                        FieldCompletionEvidence.job_id == job_id,
                    )
                )
            ).all()
        )
        commercial, non_billable_reason = await self._commercial_authorization(
            session, context=context, job_id=job_id
        )
        if commercial != "missing":
            evidence_codes.add("commercial_authorization")
        requirements = (
            tuple(snapshot.requirements) if snapshot else self.COMPLETION_REQUIREMENTS
        )
        missing = tuple(code for code in requirements if code not in evidence_codes)
        return FieldJobState(
            job_id=job_id,
            assignment_id=assignment.id,
            work_summary_recorded=summary is not None,
            customer_disposition=approval.disposition if approval else None,
            completion_ready=not missing
            and assignment.status != "reconciliation_required",
            requirement_snapshot_version=snapshot.version if snapshot else None,
            missing_requirements=missing,
            commercial_authorization=commercial,
            non_billable_reason=non_billable_reason,
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
            assignment, _job = await self._locked_scope(
                session,
                context,
                job_id,
                payload.expected_job_version,
                payload.expected_assignment_version,
            )
            snapshot = await self._ensure_snapshot(session, context, assignment)
            prior = await session.scalar(
                select(FieldWorkNote).where(
                    FieldWorkNote.company_id == context.company.id,
                    FieldWorkNote.idempotency_key == payload.idempotency_key,
                )
            )
            normalized = payload.content.strip()
            if prior is not None:
                if (
                    prior.job_id != job_id
                    or prior.note_type != payload.note_type
                    or prior.content != normalized
                ):
                    raise FieldServiceConflict(
                        "Idempotency key was already used with different note data."
                    )
            else:
                note = FieldWorkNote(
                    company_id=context.company.id,
                    branch_id=assignment.branch_id,
                    job_id=job_id,
                    assignment_id=assignment.id,
                    note_type=payload.note_type,
                    content=normalized,
                    idempotency_key=payload.idempotency_key,
                    recorded_by_user_id=context.user.id,
                )
                session.add(note)
                await session.flush()
                if payload.note_type == "work_performed":
                    await self._record_evidence(
                        session,
                        context,
                        snapshot,
                        "work_performed_summary",
                        "field_note",
                        note.id,
                    )
                self._event(
                    session,
                    context,
                    EventType.FIELD_NOTE_RECORDED,
                    note.id,
                    job_id,
                    assignment.branch_id,
                    {
                        "note_type": payload.note_type,
                        "assignment_id": str(assignment.id),
                    },
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
            assignment, job = await self._locked_scope(
                session,
                context,
                job_id,
                payload.expected_job_version,
                payload.expected_assignment_version,
            )
            snapshot = await self._ensure_snapshot(session, context, assignment)
            prior = await session.scalar(
                select(FieldCustomerApproval).where(
                    FieldCustomerApproval.company_id == context.company.id,
                    FieldCustomerApproval.idempotency_key == payload.idempotency_key,
                )
            )
            customer_name = (payload.customer_name or "").strip() or None
            reason = (payload.reason or "").strip() or None
            if prior is not None:
                if (
                    prior.job_id != job_id
                    or prior.disposition != payload.disposition
                    or prior.customer_name != customer_name
                    or prior.reason != reason
                ):
                    raise FieldServiceConflict(
                        "Idempotency key was already used with different approval data."
                    )
            else:
                approval = FieldCustomerApproval(
                    company_id=context.company.id,
                    branch_id=assignment.branch_id,
                    job_id=job_id,
                    assignment_id=assignment.id,
                    disposition=payload.disposition,
                    customer_name=customer_name,
                    reason=reason,
                    idempotency_key=payload.idempotency_key,
                    recorded_by_user_id=context.user.id,
                )
                session.add(approval)
                await session.flush()
                await self._record_evidence(
                    session,
                    context,
                    snapshot,
                    "customer_disposition",
                    "field_customer_approval",
                    approval.id,
                )
                self._event(
                    session,
                    context,
                    EventType.FIELD_CUSTOMER_APPROVAL_RECORDED,
                    approval.id,
                    job.id,
                    assignment.branch_id,
                    {
                        "disposition": payload.disposition,
                        "assignment_id": str(assignment.id),
                    },
                )
        return await self.state(session, context=context, job_id=job_id)

    async def non_billable(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        payload: NonBillableInput,
    ) -> FieldJobState:
        reason = payload.reason.strip()
        async with session.begin():
            assignment, job = await self._locked_scope(
                session,
                context,
                job_id,
                payload.expected_job_version,
                payload.expected_assignment_version,
            )
            snapshot = await self._ensure_snapshot(session, context, assignment)
            prior = await session.scalar(
                select(FieldNonBillableDisposition).where(
                    FieldNonBillableDisposition.company_id == context.company.id,
                    FieldNonBillableDisposition.idempotency_key
                    == payload.idempotency_key,
                )
            )
            if prior is not None:
                if prior.job_id != job_id or prior.reason != reason:
                    raise FieldServiceConflict(
                        "Idempotency key was already used with different non-billable data."
                    )
            else:
                existing = await session.scalar(
                    select(FieldNonBillableDisposition).where(
                        FieldNonBillableDisposition.company_id == context.company.id,
                        FieldNonBillableDisposition.job_id == job_id,
                    )
                )
                if existing is not None:
                    raise FieldServiceConflict(
                        "A non-billable disposition already exists for this Job."
                    )
                disposition = FieldNonBillableDisposition(
                    company_id=context.company.id,
                    branch_id=assignment.branch_id,
                    job_id=job_id,
                    assignment_id=assignment.id,
                    reason=reason,
                    idempotency_key=payload.idempotency_key,
                    authorized_by_user_id=context.user.id,
                )
                session.add(disposition)
                await session.flush()
                await self._record_evidence(
                    session,
                    context,
                    snapshot,
                    "commercial_authorization",
                    "field_non_billable_disposition",
                    disposition.id,
                )
                self._event(
                    session,
                    context,
                    EventType.FIELD_NON_BILLABLE_AUTHORIZED,
                    disposition.id,
                    job.id,
                    assignment.branch_id,
                    {"assignment_id": str(assignment.id)},
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
            assignment, job = await self._locked_scope(
                session,
                context,
                job_id,
                payload.expected_job_version,
                payload.expected_assignment_version,
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
            replay = await session.scalar(
                select(FieldInvoiceHandoff).where(
                    FieldInvoiceHandoff.company_id == context.company.id,
                    FieldInvoiceHandoff.idempotency_key == payload.idempotency_key,
                )
            )
            if replay is not None and replay.job_id != job_id:
                raise FieldServiceConflict(
                    "Idempotency key was already used for a different handoff."
                )
            status = "completed" if invoice else "pending"
            if handoff is None:
                handoff = FieldInvoiceHandoff(
                    company_id=context.company.id,
                    branch_id=assignment.branch_id,
                    job_id=job_id,
                    assignment_id=assignment.id,
                    invoice_id=invoice.id if invoice else None,
                    status=status,
                    idempotency_key=payload.idempotency_key,
                    requested_by_user_id=context.user.id,
                )
                session.add(handoff)
                await session.flush()
                self._event(
                    session,
                    context,
                    EventType.FIELD_INVOICE_HANDOFF_REQUESTED,
                    handoff.id,
                    job.id,
                    assignment.branch_id,
                    {"assignment_id": str(assignment.id)},
                )
            else:
                if (
                    replay is None
                    and handoff.idempotency_key != payload.idempotency_key
                ):
                    handoff.idempotency_key = payload.idempotency_key
                handoff.invoice_id = invoice.id if invoice else None
                handoff.status = status
                handoff.updated_at = datetime.now(timezone.utc)
            if invoice is not None:
                self._event(
                    session,
                    context,
                    EventType.FIELD_INVOICE_HANDOFF_COMPLETED,
                    handoff.id,
                    job.id,
                    assignment.branch_id,
                    {"invoice_id": str(invoice.id)},
                )
        return await self.state(session, context=context, job_id=job_id)

    async def _locked_scope(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        job_id: UUID,
        expected_job_version: int,
        expected_assignment_version: int,
    ) -> tuple[DispatchAssignment, Job]:
        assignment = await self._assigned_job(session, context, job_id, for_update=True)
        job = await session.scalar(
            select(Job)
            .where(
                Job.company_id == context.company.id,
                Job.branch_id == assignment.branch_id,
                Job.id == job_id,
            )
            .with_for_update()
        )
        if job is None:
            raise FieldServiceNotFound("Assigned field Job was not found.")
        if job.concurrency_version != expected_job_version:
            raise FieldServiceConflict("Job version is stale; refresh before retrying.")
        if assignment.version != expected_assignment_version:
            raise FieldServiceConflict(
                "Assignment version is stale; refresh before retrying."
            )
        return assignment, job

    async def _ensure_snapshot(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        assignment: DispatchAssignment,
    ) -> FieldCompletionRequirementSnapshot:
        snapshot = await session.scalar(
            select(FieldCompletionRequirementSnapshot)
            .where(
                FieldCompletionRequirementSnapshot.company_id == context.company.id,
                FieldCompletionRequirementSnapshot.job_id == assignment.job_id,
            )
            .with_for_update()
        )
        if snapshot is not None:
            return snapshot
        requirements = list(self.COMPLETION_REQUIREMENTS)
        fingerprint = hashlib.sha256(
            json.dumps(requirements, separators=(",", ":")).encode()
        ).hexdigest()
        snapshot = FieldCompletionRequirementSnapshot(
            company_id=context.company.id,
            branch_id=assignment.branch_id,
            job_id=assignment.job_id,
            assignment_id=assignment.id,
            version=1,
            requirements=requirements,
            requirements_fingerprint=fingerprint,
            created_by_user_id=context.user.id,
        )
        session.add(snapshot)
        await session.flush()
        return snapshot

    @staticmethod
    async def _record_evidence(
        session: AsyncSession,
        context: AuthorizationContext,
        snapshot: FieldCompletionRequirementSnapshot,
        requirement_code: str,
        source_type: str,
        source_id: UUID,
    ) -> None:
        existing = await session.scalar(
            select(FieldCompletionEvidence.id).where(
                FieldCompletionEvidence.company_id == context.company.id,
                FieldCompletionEvidence.snapshot_id == snapshot.id,
                FieldCompletionEvidence.requirement_code == requirement_code,
            )
        )
        if existing is None:
            session.add(
                FieldCompletionEvidence(
                    company_id=context.company.id,
                    branch_id=snapshot.branch_id,
                    job_id=snapshot.job_id,
                    snapshot_id=snapshot.id,
                    requirement_code=requirement_code,
                    source_type=source_type,
                    source_id=source_id,
                    recorded_by_user_id=context.user.id,
                )
            )

    async def _commercial_authorization(
        self, session: AsyncSession, *, context: AuthorizationContext, job_id: UUID
    ) -> tuple[Literal["accepted_estimate", "non_billable", "missing"], str | None]:
        accepted = await session.scalar(
            select(Estimate.id)
            .join(
                EstimateJobConversion,
                (EstimateJobConversion.company_id == Estimate.company_id)
                & (EstimateJobConversion.estimate_id == Estimate.id),
            )
            .where(
                Estimate.company_id == context.company.id,
                Estimate.branch_id.in_(context.authorized_branch_ids),
                EstimateJobConversion.job_id == job_id,
                Estimate.status.in_(("approved", "accepted")),
                Estimate.acceptance_status.in_(("approved", "accepted")),
            )
            .limit(1)
        )
        if accepted is not None:
            return "accepted_estimate", None
        non_billable = await session.scalar(
            select(FieldNonBillableDisposition).where(
                FieldNonBillableDisposition.company_id == context.company.id,
                FieldNonBillableDisposition.job_id == job_id,
                FieldNonBillableDisposition.active.is_(True),
            )
        )
        return (
            ("non_billable", non_billable.reason)
            if non_billable is not None
            else ("missing", None)
        )

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: EventType,
        entity_id: UUID,
        job_id: UUID,
        branch_id: UUID,
        payload: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="field_job",
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                correlation_id=uuid4(),
                payload={"job_id": str(job_id), **payload},
            ),
        )

    async def _assigned_job(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> DispatchAssignment:
        employee = await self._employee(session, context)
        crew = select(DispatchCrewMember.assignment_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.employee_id == employee.id,
            DispatchCrewMember.status == "active",
        )
        query = (
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
        if for_update:
            query = query.with_for_update()
        assignment = await session.scalar(query)
        if assignment is None:
            raise FieldServiceNotFound("Assigned field Job was not found.")
        return assignment

    @staticmethod
    def _service_day_bounds(
        service_date: date, timezone_name: str
    ) -> tuple[datetime, datetime]:
        try:
            business_zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise FieldServiceValidation(
                "The configured business timezone is invalid."
            ) from error
        return (
            datetime.combine(service_date, time.min, tzinfo=business_zone).astimezone(
                timezone.utc
            ),
            datetime.combine(service_date, time.max, tzinfo=business_zone).astimezone(
                timezone.utc
            ),
        )

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
