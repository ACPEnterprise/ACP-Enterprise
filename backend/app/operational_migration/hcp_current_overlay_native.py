"""Native domain-service implementation for safe HCP current overlays."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    CustomerSourceIdentity,
    ServiceLocationSourceIdentity,
)
from app.customers.models import Customer, ServiceLocation
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerStatus,
    CustomerType,
    CustomerUpdateRequest,
    ServiceLocationCreate,
)
from app.customers.service import CustomerService
from app.customers.update import CustomerUpdateService, customer_update_service
from app.jobs.commands import MigrateJob, UpdateJob
from app.jobs.models import Job, JobAppointmentLink
from app.jobs.service import JobService
from app.jobs.types import JobPriority
from app.operational_migration.hcp_current_overlay import (
    OverlayDomainHold,
    OverlayKey,
    OverlayRecord,
    OverlaySourceState,
)
from app.operational_migration.hcp_current_overlay_adapter import (
    CurrentOverlayDomainServices,
)
from app.operational_migration.hcp_source4_contracts import JOB_STATUS
from app.operational_migration.models import (
    AppointmentSourceIdentity,
    HcpMigrationHold,
    JobSourceIdentity,
)
from app.operational_migration.repository import OperationalMigrationRepository
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment
from app.scheduling.service import (
    MigrateAppointmentCommand,
    RescheduleAppointmentCommand,
    SchedulingService,
)
from app.scheduling.types import (
    AppointmentReference,
    AppointmentRescheduleReason,
    AppointmentStatus,
)

SOURCE_SYSTEM = "housecall_pro_source4"
TRANSFORMATION_VERSION = "hcp-current-native-overlay/v1"


class HcpCurrentOverlayNativeServices(CurrentOverlayDomainServices):
    """Apply validated operational assertions through existing domain services."""

    def __init__(
        self,
        *,
        context: AuthorizationContext,
        master_run_id: UUID,
        customer_run_id: UUID,
        operational_run_id: UUID,
        package_digest: str,
        base_source_digests: Mapping[OverlayKey, str],
        customers: CustomerService | None = None,
        customer_updates: CustomerUpdateService = customer_update_service,
        jobs: JobService | None = None,
        scheduling: SchedulingService | None = None,
        repository: OperationalMigrationRepository | None = None,
    ) -> None:
        if context.active_branch is None:
            raise ValueError("overlay requires active Branch scope")
        self.context = context
        self.branch = context.active_branch
        self.master_run_id = master_run_id
        self.customer_run_id = customer_run_id
        self.operational_run_id = operational_run_id
        self.package_digest = package_digest
        self.base_source_digests = dict(base_source_digests)
        self.customers = customers or CustomerService()
        self.customer_updates = customer_updates
        self.jobs = jobs or JobService()
        self.scheduling = scheduling or SchedulingService()
        self.repository = repository or OperationalMigrationRepository()

    async def source_state(
        self, session: AsyncSession, key: OverlayKey
    ) -> OverlaySourceState | None:
        target = await self._target(session, key)
        if target is None:
            return None
        digest = self.base_source_digests.get(key)
        metadata = getattr(target[0], "external_metadata", None)
        if isinstance(metadata, dict):
            digest = str(metadata.get("current_overlay_source_digest") or digest or "")
        if not digest:
            raise ValueError("bound source identity lacks base digest authority")
        return OverlaySourceState(digest, str(target[1].id), {})

    async def source_exists(self, session: AsyncSession, key: OverlayKey) -> bool:
        return await self._target(session, key) is not None

    async def fingerprint_owners(
        self, session: AsyncSession, domain: str, fingerprint: str
    ) -> tuple[str, ...]:
        if domain == "service_location":
            values = await session.scalars(
                select(ServiceLocationSourceIdentity.service_location_id).where(
                    ServiceLocationSourceIdentity.company_id
                    == self.context.company.id,
                    ServiceLocationSourceIdentity.source_digest == fingerprint,
                )
            )
        elif domain == "job":
            values = await session.scalars(
                select(JobSourceIdentity.job_id).where(
                    JobSourceIdentity.company_id == self.context.company.id,
                    JobSourceIdentity.external_metadata[
                        "current_overlay_source_digest"
                    ].astext
                    == fingerprint,
                )
            )
        elif domain == "appointment":
            values = await session.scalars(
                select(AppointmentSourceIdentity.appointment_id).where(
                    AppointmentSourceIdentity.company_id == self.context.company.id,
                    AppointmentSourceIdentity.external_metadata[
                        "current_overlay_source_digest"
                    ].astext
                    == fingerprint,
                )
            )
        else:
            # Customer source uniqueness and the qualified canonical classifier are
            # the durable duplicate boundary; Customer identities carry no digest.
            return ()
        return tuple(sorted(str(value) for value in values.all()))

    async def create(
        self, session: AsyncSession, record: OverlayRecord
    ) -> OverlaySourceState:
        if record.domain == "customer":
            native: Any = await self._create_customer(session, record)
        elif record.domain == "service_location":
            native = await self._create_location(session, record)
        elif record.domain == "job":
            native = await self._create_job(session, record)
        elif record.domain == "appointment":
            native = await self._create_appointment(session, record)
        else:
            raise ValueError("financial overlay mutation is prohibited")
        return OverlaySourceState(record.source_digest, str(native.id), record.payload)

    async def update(
        self,
        session: AsyncSession,
        state: OverlaySourceState,
        record: OverlayRecord,
    ) -> OverlaySourceState:
        if record.domain == "customer":
            native = await self._update_customer(session, state, record)
        elif record.domain == "job":
            native = await self._update_job(session, state, record)
        elif record.domain == "appointment":
            native = await self._update_appointment(session, state, record)
        else:
            raise ValueError("this overlay domain does not permit updates")
        await self._stamp_identity(session, record)
        return OverlaySourceState(record.source_digest, str(native.id), record.payload)

    async def record_non_mutating_assertion(
        self, session: AsyncSession, record: OverlayRecord
    ) -> None:
        digest = _digest(
            {
                "master_run_id": str(self.master_run_id),
                "domain": record.domain,
                "source_id": record.source_id,
                "assertion": record.assertion.value,
                "source_digest": record.source_digest,
                "reason": record.reason,
            }
        )
        existing = await session.scalar(
            select(HcpMigrationHold).where(
                HcpMigrationHold.company_id == self.context.company.id,
                HcpMigrationHold.hold_digest == digest,
            )
        )
        if existing is not None:
            return
        session.add(
            HcpMigrationHold(
                company_id=self.context.company.id,
                branch_id=self.branch.id,
                master_run_id=self.master_run_id,
                entity_kind=record.domain,
                native_id=record.source_id,
                hold_code=record.reason or f"overlay_{record.assertion.value}",
                package_digest=self.package_digest,
                evidence_digest=record.source_digest,
                reconciliation_key=f"{record.domain}:{record.source_id}"[:191],
                state="HELD",
                hold_digest=digest,
                evidence_version=1,
                operational_effects_enabled=False,
                financial_truth_accepted=False,
            )
        )

    async def _create_customer(self, session: AsyncSession, record: OverlayRecord) -> Customer:
        payload = record.payload
        first = _text(payload.get("first_name"))
        last = _text(payload.get("last_name"))
        company = _text(payload.get("company"))
        display_name = company or " ".join(value for value in (first, last) if value)
        if not display_name:
            raise ValueError("source Customer has no authoritative display name")
        customer = await self.customers.stage_migrated_customer(
            session,
            context=self.context,
            customer_data=CustomerCreate(
                customer_type=(
                    CustomerType.COMMERCIAL
                    if payload.get("kind") == "business"
                    else CustomerType.RESIDENTIAL
                ),
                display_name=display_name,
                legal_name=company,
                marketing_source=_text(payload.get("lead_source")),
                notes=_text(payload.get("notes")),
                status=CustomerStatus.ACTIVE,
            ),
            contact_data=ContactCreate(
                first_name=first,
                last_name=last,
                email=_text(payload.get("email")),
                mobile_phone=_text(payload.get("mobile_number")),
                office_phone=_text(payload.get("work_number")),
                is_preferred=True,
                active=True,
            )
            if first and last
            else None,
            service_location_data=None,
            billing_address_data=None,
        )
        session.add(
            CustomerSourceIdentity(
                company_id=self.context.company.id,
                branch_id=self.branch.id,
                customer_id=customer.id,
                source_system=SOURCE_SYSTEM,
                source_customer_id=record.source_id,
                first_run_id=self.customer_run_id,
            )
        )
        await session.flush()
        return customer

    async def _create_location(self, session: AsyncSession, record: OverlayRecord):
        customer_identity = await self._customer_identity(session, record.parent_keys)
        data = _location(record.payload)
        location = await self.customers.stage_migrated_service_location(
            session,
            context=self.context,
            customer_id=customer_identity.customer_id,
            data=data,
        )
        session.add(
            ServiceLocationSourceIdentity(
                company_id=self.context.company.id,
                branch_id=self.branch.id,
                master_run_id=self.master_run_id,
                customer_source_identity_id=customer_identity.id,
                service_location_id=location.id,
                customer_id=customer_identity.customer_id,
                source_system=SOURCE_SYSTEM,
                source_location_id=record.source_id,
                source_digest=record.source_digest,
                package_digest=self.package_digest,
                transformation_version=TRANSFORMATION_VERSION,
                transformation_digest=_digest(record.payload),
                source_context={"acquired_at": record.acquired_at},
                first_run_id=self.customer_run_id,
            )
        )
        await session.flush()
        return location

    async def _create_job(self, session: AsyncSession, record: OverlayRecord) -> Job:
        customer, location = await self._job_parents(session, record.parent_keys)
        payload = record.payload
        status = _job_status(payload)
        if status == "cancelled":
            raise OverlayDomainHold(
                "cancelled Job requires unsupported lifecycle detail and remains held"
            )
        timestamps = _mapping(payload.get("work_timestamps"))
        created = _datetime(payload.get("created_at"))
        started = _datetime(timestamps.get("started_at"))
        completed = _datetime(timestamps.get("completed_at"))
        job = await self.jobs.stage_migrated_job(
            session,
            context=self.context,
            command=MigrateJob(
                branch_id=self.branch.id,
                customer_id=customer.customer_id,
                service_location_id=location.service_location_id,
                status=status,
                priority=JobPriority.NORMAL,
                customer_reported_problem=_text(payload.get("description")),
                internal_description=None,
                activated_at=created if status != "draft" else None,
                started_at=started if status in {"in_progress", "completed"} else None,
                completed_at=completed if status == "completed" else None,
            ),
        )
        identity = JobSourceIdentity(
            company_id=self.context.company.id,
            branch_id=self.branch.id,
            job_id=job.id,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            customer_source_identity_id=customer.id,
            service_location_source_identity_id=location.id,
            source_system=SOURCE_SYSTEM,
            source_job_id=record.source_id,
            source_job_number=_text(payload.get("invoice_number")),
            source_status=str(payload.get("work_status") or ""),
            assigned_technician_source_ids=_technicians(payload),
            external_metadata=_metadata(record),
            first_run_id=self.operational_run_id,
        )
        session.add(identity)
        await session.flush()
        return job

    async def _create_appointment(self, session: AsyncSession, record: OverlayRecord) -> Appointment:
        job_identity, job = await self._appointment_parent(session, record.parent_keys)
        start = _datetime(record.payload.get("start_time"))
        end = _datetime(record.payload.get("end_time"))
        if job.status == "cancelled":
            raise OverlayDomainHold(
                "cancelled Appointment requires unsupported lifecycle detail"
            )
        status = (
            AppointmentStatus.COMPLETED
            if job.status == "completed"
            else AppointmentStatus.SCHEDULED
            if start and end
            else AppointmentStatus.DRAFT
        )
        appointment = await self.scheduling.stage_migrated_appointment(
            session,
            context=self.context,
            command=MigrateAppointmentCommand(
                branch_id=self.branch.id,
                customer_id=job.customer_id,
                service_location_id=job.service_location_id,
                status=status,
                arrival_window_start_at=start,
                arrival_window_end_at=end,
                expected_duration_minutes=(
                    int((end - start).total_seconds() // 60) if start and end else None
                ),
            ),
        )
        visit_sequence = 1 + int(
            await session.scalar(
                select(func.coalesce(func.max(JobAppointmentLink.visit_sequence), 0))
                .where(JobAppointmentLink.job_id == job.id)
            )
            or 0
        )
        await self.jobs.stage_migrated_appointment_link(
            session,
            context=self.context,
            job=job,
            appointment=AppointmentReference(
                id=appointment.id,
                company_id=appointment.company_id,
                branch_id=appointment.branch_id,
                customer_id=appointment.customer_id,
                service_location_id=appointment.service_location_id,
                status=status,
            ),
            visit_sequence=visit_sequence,
        )
        session.add(
            AppointmentSourceIdentity(
                company_id=self.context.company.id,
                branch_id=self.branch.id,
                appointment_id=appointment.id,
                job_source_identity_id=job_identity.id,
                job_id=job.id,
                customer_id=job.customer_id,
                service_location_id=job.service_location_id,
                source_system=SOURCE_SYSTEM,
                source_appointment_id=record.source_id,
                source_status=status.value,
                assigned_technician_source_ids=_string_list(
                    record.payload.get("dispatched_employees_ids")
                ),
                external_metadata=_metadata(record),
                first_run_id=self.operational_run_id,
            )
        )
        await session.flush()
        return appointment

    async def _update_customer(self, session: AsyncSession, state: OverlaySourceState, record: OverlayRecord):
        payload = record.payload
        customer = await session.get(Customer, UUID(state.native_id), with_for_update=True)
        if customer is None or customer.company_id != self.context.company.id:
            raise ValueError("overlay Customer target is missing or out of scope")
        source_updated_at = _datetime(payload.get("updated_at"))
        if source_updated_at and customer.updated_at > source_updated_at:
            raise OverlayDomainHold(
                "newer native Customer state is authoritative and remains unchanged"
            )
        first, last = _text(payload.get("first_name")), _text(payload.get("last_name"))
        company = _text(payload.get("company"))
        display_name = company or " ".join(value for value in (first, last) if value)
        return await self.customer_updates.stage_update(
            session,
            context=self.context,
            customer_id=UUID(state.native_id),
            data=CustomerUpdateRequest(
                display_name=display_name or None,
                legal_name=company,
                marketing_source=_text(payload.get("lead_source")),
                notes=_text(payload.get("notes")),
                first_name=first,
                last_name=last,
                business_name=company,
                primary_phone=_text(payload.get("mobile_number")),
                secondary_phone=_text(payload.get("home_number")),
                email=_text(payload.get("email")),
            ),
        )

    async def _update_job(self, session: AsyncSession, state: OverlaySourceState, record: OverlayRecord):
        job = await session.get(Job, UUID(state.native_id), with_for_update=True)
        if job is None or job.company_id != self.context.company.id:
            raise ValueError("overlay Job target is missing or out of scope")
        source_updated_at = _datetime(record.payload.get("updated_at"))
        if source_updated_at and job.updated_at > source_updated_at:
            raise OverlayDomainHold(
                "newer native Job state is authoritative and remains unchanged"
            )
        if job.status != _job_status(record.payload):
            raise OverlayDomainHold("overlay Job lifecycle conflict must remain held")
        if job.status not in {"draft", "ready"}:
            raise OverlayDomainHold(
                "historical Job metadata is non-authoritative and remains held"
            )
        return await self.jobs.stage_update_job(
            session,
            context=self.context,
            command=UpdateJob(
                job_id=job.id,
                expected_version=job.concurrency_version,
                customer_reported_problem=_text(record.payload.get("description")),
            ),
        )

    async def _update_appointment(self, session: AsyncSession, state: OverlaySourceState, record: OverlayRecord):
        appointment = await session.get(Appointment, UUID(state.native_id), with_for_update=True)
        if appointment is None or appointment.company_id != self.context.company.id:
            raise ValueError("overlay Appointment target is missing or out of scope")
        start = _datetime(record.payload.get("start_time"))
        end = _datetime(record.payload.get("end_time"))
        if appointment.status not in {"scheduled", "confirmed"} or not start or not end:
            raise OverlayDomainHold(
                "overlay Appointment lifecycle conflict must remain held"
            )
        acquired_at = _datetime(record.acquired_at)
        if acquired_at is not None and end < acquired_at:
            raise OverlayDomainHold(
                "historical Appointment window is not rescheduled into native truth"
            )
        if (appointment.arrival_window_start_at, appointment.arrival_window_end_at) == (start, end):
            return appointment
        return await self.scheduling.stage_reschedule_appointment(
            session,
            context=self.context,
            command=RescheduleAppointmentCommand(
                appointment_id=appointment.id,
                expected_version=appointment.concurrency_version,
                arrival_window_start_at=start,
                arrival_window_end_at=end,
                expected_duration_minutes=int((end - start).total_seconds() // 60),
                capacity_units=Decimal("1.00"),
                reason_code=AppointmentRescheduleReason.OPERATIONAL_ADJUSTMENT,
            ),
        )

    async def _stamp_identity(self, session: AsyncSession, record: OverlayRecord) -> None:
        target = await self._target(session, record.key)
        if target is None:
            raise ValueError("overlay source identity disappeared")
        identity = target[0]
        if hasattr(identity, "external_metadata"):
            metadata = dict(identity.external_metadata or {})
            metadata.update(_metadata(record))
            identity.external_metadata = metadata

    async def _target(self, session: AsyncSession, key: OverlayKey):
        company_id = self.context.company.id
        if key.domain == "customer":
            customer_identity = await self.repository.get_customer_identity(
                session, company_id=company_id, branch_id=self.branch.id,
                source_system=SOURCE_SYSTEM, source_customer_id=key.source_id
            )
            return (
                customer_identity,
                await session.get(Customer, customer_identity.customer_id),
            ) if customer_identity else None
        if key.domain == "service_location":
            location_identity = await session.scalar(select(ServiceLocationSourceIdentity).where(
                ServiceLocationSourceIdentity.company_id == company_id,
                ServiceLocationSourceIdentity.source_system == SOURCE_SYSTEM,
                ServiceLocationSourceIdentity.source_location_id == key.source_id))
            return (
                location_identity,
                await session.get(
                    ServiceLocation, location_identity.service_location_id
                ),
            ) if location_identity else None
        if key.domain == "job":
            job_identity = await self.repository.get_job_identity(session, company_id=company_id, source_system=SOURCE_SYSTEM, source_job_id=key.source_id)
            return (job_identity, await session.get(Job, job_identity.job_id)) if job_identity else None
        if key.domain == "appointment":
            appointment_identity = await self.repository.get_appointment_identity(session, company_id=company_id, source_system=SOURCE_SYSTEM, source_appointment_id=key.source_id)
            return (appointment_identity, await session.get(Appointment, appointment_identity.appointment_id)) if appointment_identity else None
        return None

    async def _customer_identity(self, session: AsyncSession, parents: tuple[OverlayKey, ...]):
        key = next((item for item in parents if item.domain == "customer"), None)
        if key is None:
            raise ValueError("Location Customer parent is missing")
        identity = await self.repository.get_customer_identity(session, company_id=self.context.company.id, branch_id=self.branch.id, source_system=SOURCE_SYSTEM, source_customer_id=key.source_id)
        if identity is None:
            raise ValueError("Location Customer parent is unresolved")
        return identity

    async def _job_parents(self, session: AsyncSession, parents: tuple[OverlayKey, ...]):
        customer = await self._customer_identity(session, parents)
        key = next((item for item in parents if item.domain == "service_location"), None)
        if key is None:
            raise ValueError("Job Location parent is missing")
        location = await self.repository.get_location_identity(session, company_id=self.context.company.id, customer_source_identity_id=customer.id, source_system=SOURCE_SYSTEM, source_location_id=key.source_id)
        if location is None:
            raise ValueError("Job Location parent is unresolved")
        return customer, location

    async def _appointment_parent(self, session: AsyncSession, parents: tuple[OverlayKey, ...]):
        key = next((item for item in parents if item.domain == "job"), None)
        if key is None:
            raise ValueError("Appointment Job parent is missing")
        identity = await self.repository.get_job_identity(session, company_id=self.context.company.id, source_system=SOURCE_SYSTEM, source_job_id=key.source_id)
        job = (
            await session.get(Job, identity.job_id, with_for_update=True)
            if identity
            else None
        )
        if identity is None or job is None:
            raise ValueError("Appointment Job parent is unresolved")
        return identity, job


def _text(value: object) -> str | None:
    result = str(value).strip() if value is not None else ""
    return result or None


def _datetime(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None


def _job_status(payload: Mapping[str, object]) -> str:
    source = str(payload.get("work_status") or "")
    try:
        return JOB_STATUS[source]
    except KeyError as error:
        raise ValueError("unsupported HCP Job lifecycle") from error


def _technicians(payload: Mapping[str, object]) -> list[str]:
    employees = payload.get("assigned_employees")
    return [
        str(item["id"])
        for item in employees
        if isinstance(item, Mapping) and item.get("id")
    ] if isinstance(employees, list) else []


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _location(payload: Mapping[str, object]) -> ServiceLocationCreate:
    if not all(payload.get(key) for key in ("street", "city", "state", "zip")):
        raise OverlayDomainHold("source Location address is incomplete")
    country = str(payload.get("country") or "US").upper()
    if country in {"USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
        country = "US"
    return ServiceLocationCreate(nickname=_text(payload.get("type")), address=str(payload["street"]), address_line_2=_text(payload.get("street_line_2")), city=str(payload["city"]), state=str(payload["state"]), postal_code=str(payload["zip"]), country=country, is_primary=False, active=True)


def _metadata(record: OverlayRecord) -> dict[str, object]:
    return {"current_overlay_source_digest": record.source_digest, "current_overlay_acquired_at": record.acquired_at, "current_overlay_contract": TRANSFORMATION_VERSION}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
