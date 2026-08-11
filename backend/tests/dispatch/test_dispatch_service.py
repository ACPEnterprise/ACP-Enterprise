from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers.models import Customer, ServiceLocation
from app.dispatch.errors import DispatchConflict, DispatchNotFound
from app.dispatch.models import DispatchAssignment, DispatchAssignmentHistory
from app.dispatch.service import DispatchService
from app.events.models import BusinessEvent
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.scheduling.models import Appointment
from app.workforce.models import (
    Capability,
    CapabilityCategory,
    WorkforceBranchEligibility,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)


@pytest_asyncio.fixture
async def dispatch_fixture() -> AsyncIterator[
    tuple[
        async_sessionmaker[AsyncSession],
        AuthorizationContext,
        Appointment,
        Employee,
        Employee,
    ]
]:
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    start = now + timedelta(days=1)
    end = start + timedelta(hours=2)
    async with factory() as session, session.begin():
        company = Company(
            name="Dispatch Test",
            code=f"D{uuid4().hex[:10].upper()}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code=f"B{uuid4().hex[:10].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        customer = Customer(
            company=company,
            customer_number=f"CUS-{int(uuid4().hex[:8], 16):010d}",
            status="active",
            customer_type="residential",
            display_name="Dispatch Customer",
            preferred_contact_method="phone",
            normalized_name=f"dispatch-{uuid4().hex}",
        )
        location = ServiceLocation(
            customer=customer,
            address="1 Test",
            city="Town",
            state="NY",
            postal_code="10001",
            country="US",
            normalized_address=f"1-test-{uuid4().hex}",
            active=True,
        )
        actor = User(
            normalized_email=f"dispatch-{uuid4().hex}@example.test",
            first_name="Dispatch",
            last_name="Owner",
            display_name="Dispatch Owner",
            status="active",
        )
        session.add_all([company, branch, customer, location, actor])
        await session.flush()
        membership = Membership(
            user_id=actor.id,
            company_id=company.id,
            status="active",
            has_all_branch_access=True,
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
        await session.flush()
        employees = [
            Employee(
                company_id=company.id,
                home_branch_id=branch.id,
                employee_number=f"T-{i}-{uuid4().hex[:5]}",
                first_name=f"Tech{i}",
                last_name="Test",
                display_name=f"Technician {i}",
                job_title="Service Technician",
                employee_type="employee",
                status="active",
            )
            for i in (1, 2)
        ]
        employees[0].membership_id = membership.id
        session.add_all(employees)
        await session.flush()
        category = CapabilityCategory(
            company_id=company.id,
            code=f"technical-{uuid4().hex[:6]}",
            display_name="Technical",
        )
        session.add(category)
        await session.flush()
        capability = Capability(
            company_id=company.id,
            category_id=category.id,
            code="technician",
            display_name="Technician",
        )
        session.add(capability)
        await session.flush()
        for employee in employees:
            profile = WorkforceCapabilityProfile(
                company_id=company.id, employee_id=employee.id, status="active"
            )
            session.add(profile)
            await session.flush()
            session.add_all(
                [
                    WorkforceCapability(
                        company_id=company.id,
                        profile_id=profile.id,
                        capability_id=capability.id,
                        proficiency="qualified",
                        status="active",
                    ),
                    WorkforceBranchEligibility(
                        company_id=company.id,
                        profile_id=profile.id,
                        branch_id=branch.id,
                        status="active",
                    ),
                    WorkforceWorkingAvailability(
                        company_id=company.id,
                        profile_id=profile.id,
                        branch_id=branch.id,
                        start_at=start - timedelta(hours=1),
                        end_at=end + timedelta(hours=1),
                        status="available",
                        source="test",
                    ),
                ]
            )
        appointment = Appointment(
            company_id=company.id,
            branch_id=branch.id,
            appointment_number=f"APT-{int(uuid4().hex[:6], 16) % 1000000:06d}",
            customer_id=customer.id,
            service_location_id=location.id,
            status="scheduled",
            arrival_window_start_at=start,
            arrival_window_end_at=end,
            expected_duration_minutes=120,
            scheduling_timezone="America/New_York",
        )
        session.add(appointment)
        await session.flush()
    context = AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=actor.authorization_version,
    )
    try:
        yield factory, context, appointment, employees[0], employees[1]
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_assignment_is_idempotent_audited_and_releasable(dispatch_fixture):
    factory, context, appointment, technician, _ = dispatch_fixture
    service = DispatchService()
    async with factory() as session:
        eligible = await service.eligible(
            session, context=context, appointment_id=appointment.id
        )
        assert (
            next(
                item for item in eligible if item.employee_id == technician.id
            ).decision
            == "eligible"
        )
    async with factory() as session:
        first = await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=technician.id,
            reason="Primary coverage",
            idempotency_key="dispatch-assign-001",
        )
    async with factory() as session:
        duplicate = await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=technician.id,
            reason="Primary coverage",
            idempotency_key="dispatch-assign-001",
        )
    assert duplicate.id == first.id and duplicate.version == first.version
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count(DispatchAssignment.id)).where(
                    DispatchAssignment.appointment_id == appointment.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(DispatchAssignmentHistory.id)).where(
                    DispatchAssignmentHistory.assignment_id == first.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.entity_id == first.id
                )
            )
            == 1
        )
    async with factory() as session:
        released = await service.release(
            session,
            context=context,
            appointment_id=appointment.id,
            reason="Work removed",
            idempotency_key="dispatch-release-001",
            expected_version=first.version,
        )
    assert released.status == "released"


@pytest.mark.asyncio
async def test_overlapping_assignment_and_company_scope_fail_closed(dispatch_fixture):
    factory, context, appointment, technician, _ = dispatch_fixture
    service = DispatchService()
    async with factory() as session:
        await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=technician.id,
            reason="Primary",
            idempotency_key="dispatch-overlap-001",
        )
    async with factory() as session, session.begin():
        other = Appointment(
            company_id=context.company.id,
            branch_id=appointment.branch_id,
            appointment_number=f"APT-{int(uuid4().hex[:6], 16) % 1000000:06d}",
            customer_id=appointment.customer_id,
            service_location_id=appointment.service_location_id,
            status="scheduled",
            arrival_window_start_at=appointment.arrival_window_start_at
            + timedelta(minutes=30),
            arrival_window_end_at=appointment.arrival_window_end_at
            + timedelta(minutes=30),
            expected_duration_minutes=120,
            scheduling_timezone="America/New_York",
        )
        session.add(other)
        await session.flush()
        other_id = other.id
    async with factory() as session:
        with pytest.raises(DispatchConflict, match="conflicting_assignment"):
            await service.assign(
                session,
                context=context,
                appointment_id=other_id,
                employee_id=technician.id,
                reason="Overlap",
                idempotency_key="dispatch-overlap-002",
            )
        with pytest.raises(DispatchNotFound):
            await service.detail(session, context=context, appointment_id=uuid4())


@pytest.mark.asyncio
async def test_missing_availability_is_reported_unknown(dispatch_fixture):
    factory, context, appointment, _, technician = dispatch_fixture
    async with factory() as session, session.begin():
        profile_id = await session.scalar(
            select(WorkforceCapabilityProfile.id).where(
                WorkforceCapabilityProfile.employee_id == technician.id
            )
        )
        availability = await session.scalar(
            select(WorkforceWorkingAvailability).where(
                WorkforceWorkingAvailability.profile_id == profile_id
            )
        )
        await session.delete(availability)
    async with factory() as session:
        option = next(
            item
            for item in await DispatchService().eligible(
                session, context=context, appointment_id=appointment.id
            )
            if item.employee_id == technician.id
        )
        assert option.decision == "availability_unknown" and not option.eligible


@pytest.mark.asyncio
async def test_job_title_does_not_substitute_for_workforce_capability(
    dispatch_fixture,
):
    factory, context, appointment, technician, _ = dispatch_fixture
    async with factory() as session, session.begin():
        profile_id = await session.scalar(
            select(WorkforceCapabilityProfile.id).where(
                WorkforceCapabilityProfile.employee_id == technician.id
            )
        )
        capability = await session.scalar(
            select(WorkforceCapability).where(
                WorkforceCapability.profile_id == profile_id
            )
        )
        await session.delete(capability)
    async with factory() as session:
        option = next(
            item
            for item in await DispatchService().eligible(
                session, context=context, appointment_id=appointment.id
            )
            if item.employee_id == technician.id
        )
    assert option.decision == "missing_required_capability"
    assert not option.eligible


@pytest.mark.asyncio
async def test_crew_replacement_and_reconciliation_lifecycle(dispatch_fixture):
    factory, context, appointment, primary, crew = dispatch_fixture
    service = DispatchService()
    async with factory() as session:
        assigned = await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=primary.id,
            reason="Primary",
            idempotency_key="dispatch-lifecycle-assign",
        )
    async with factory() as session:
        with_crew = await service.crew(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=crew.id,
            reason="Two-person visit",
            idempotency_key="dispatch-lifecycle-crew",
            expected_version=assigned.version,
        )
    assert [item.employee_id for item in with_crew.crew_members] == [crew.id]
    async with factory() as session:
        without_crew = await service.crew(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=crew.id,
            reason="Crew no longer required",
            idempotency_key="dispatch-lifecycle-crew-remove",
            expected_version=with_crew.version,
            remove=True,
        )
    async with factory() as session:
        replaced = await service.replace(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=crew.id,
            reason="Coverage change",
            idempotency_key="dispatch-lifecycle-replace",
            expected_version=without_crew.version,
        )
    assert replaced.primary_employee_id == crew.id
    async with factory() as session:
        ambiguous = await service.reconcile(
            session,
            context=context,
            appointment_id=appointment.id,
            reason="Conflicting dispatcher evidence",
            idempotency_key="dispatch-lifecycle-ambiguous",
            expected_version=replaced.version,
        )
    assert ambiguous.status == "reconciliation_required"
    async with factory() as session:
        reconciled = await service.reconcile(
            session,
            context=context,
            appointment_id=appointment.id,
            reason="Supervisor confirmed assignment",
            idempotency_key="dispatch-lifecycle-resolved",
            expected_version=ambiguous.version,
            resolution="restore_assigned",
        )
    assert reconciled.status == "assigned"


@pytest.mark.asyncio
async def test_arrival_and_controlled_exception_evidence_is_idempotent(
    dispatch_fixture,
):
    factory, context, appointment, technician, _ = dispatch_fixture
    service = DispatchService()
    async with factory() as session:
        assigned = await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=technician.id,
            reason="Primary",
            idempotency_key="dispatch-arrival-assign",
        )
    async with factory() as session:
        en_route = await service.record_arrival(
            session,
            context=context,
            appointment_id=appointment.id,
            state="en_route",
            expected_version=assigned.version,
            idempotency_key="dispatch-arrival-en-route",
        )
    assert en_route.status == "acknowledged"
    assert en_route.arrival_state == "en_route"
    async with factory() as session:
        replay = await service.record_arrival(
            session,
            context=context,
            appointment_id=appointment.id,
            state="en_route",
            expected_version=assigned.version,
            idempotency_key="dispatch-arrival-en-route",
        )
    assert replay.version == en_route.version
    async with factory() as session:
        arrived = await service.record_arrival(
            session,
            context=context,
            appointment_id=appointment.id,
            state="arrived",
            expected_version=en_route.version,
            idempotency_key="dispatch-arrival-arrived",
        )
    assert arrived.arrival_state == "arrived"

    async with factory() as session:
        exception = await service.report_exception(
            session,
            context=context,
            appointment_id=appointment.id,
            exception_code="safety_condition",
            reason="Unsafe access",
            idempotency_key="dispatch-exception-safety",
            expected_version=arrived.version,
        )
    assert exception.status == "reconciliation_required"
    assert exception.active_exception_code == "safety_condition"
    async with factory() as session:
        replay_exception = await service.report_exception(
            session,
            context=context,
            appointment_id=appointment.id,
            exception_code="safety_condition",
            reason="Unsafe access",
            idempotency_key="dispatch-exception-safety",
            expected_version=arrived.version,
        )
    assert replay_exception.version == exception.version
    async with factory() as session:
        resolved = await service.reconcile(
            session,
            context=context,
            appointment_id=appointment.id,
            reason="Supervisor cleared access",
            idempotency_key="dispatch-exception-resolved",
            expected_version=exception.version,
            resolution="restore_assigned",
        )
    assert resolved.active_exception_code is None
    assert resolved.arrival_state == "arrived"

    async with factory() as session:
        history = await session.scalar(
            select(func.count(DispatchAssignmentHistory.id)).where(
                DispatchAssignmentHistory.assignment_id == assigned.id
            )
        )
        events = await session.scalar(
            select(func.count(BusinessEvent.id)).where(
                BusinessEvent.entity_id == assigned.id
            )
        )
    assert history == events == 5
    async with factory() as session:
        with pytest.raises(DispatchConflict, match="Idempotency key conflicts"):
            await service.report_exception(
                session,
                context=context,
                appointment_id=appointment.id,
                exception_code="other",
                reason="Contradictory replay",
                idempotency_key="dispatch-arrival-en-route",
                expected_version=resolved.version,
            )


@pytest.mark.asyncio
async def test_unassigned_employee_cannot_record_arrival(dispatch_fixture):
    factory, context, appointment, _, unlinked = dispatch_fixture
    service = DispatchService()
    async with factory() as session:
        assigned = await service.assign(
            session,
            context=context,
            appointment_id=appointment.id,
            employee_id=unlinked.id,
            reason="Primary",
            idempotency_key="dispatch-unlinked-assign",
        )
    async with factory() as session:
        with pytest.raises(DispatchNotFound):
            await service.record_arrival(
                session,
                context=context,
                appointment_id=appointment.id,
                state="en_route",
                expected_version=assigned.version,
                idempotency_key="dispatch-unlinked-arrival",
            )
