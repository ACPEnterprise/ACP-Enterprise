from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.customers.models import Customer, ServiceLocation  # noqa: F401
from app.database.session import get_database_session
from app.main import app
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.users.models import User
from app.scheduling.models import Appointment  # noqa: F401
from app.timekeeping.commands import (
    CorrectTimeEntry,
    CreatePayPeriod,
    RecordManualTime,
    RecordPunch,
)
from app.timekeeping.contracts import (
    PunchKind,
    TimeEntryProvenance,
    WorkdayAuthorizationError,
    WorkdayConflictError,
    WorkdayTimeError,
    seal_payroll_time_input,
)
from app.timekeeping.economics_adapter import to_economics_workday_time
from app.timekeeping.models import (
    PayPeriod,
    PayrollTimeInputRecord,
    WorkdayPunchEvent,
    WorkdayTimeEntryRevision,
)
from app.timekeeping.permissions import TimekeepingPermission
from app.timekeeping.service import WorkdayTimeService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

NOW = datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc)


def test_timekeeping_permissions_are_narrow_and_catalogued() -> None:
    permission_catalog.validate()
    definitions = {
        value.code: value
        for value in permission_catalog.definitions
        if value.code in TimekeepingPermission.ALL
    }
    assert set(definitions) == set(TimekeepingPermission.ALL)
    assert all(value.resource == "timekeeping" for value in definitions.values())


def test_missing_approved_time_never_seals_as_zero() -> None:
    with pytest.raises(WorkdayTimeError, match="missing is not zero"):
        seal_payroll_time_input(
            company_id=uuid4(),
            employee_id=uuid4(),
            pay_period_id=uuid4(),
            period_start=date(2026, 8, 29),
            period_end=date(2026, 9, 4),
            approved_entries=(),
        )


@dataclass(frozen=True)
class SeededTimekeeping:
    company_id: UUID
    branch_id: UUID
    user_id: UUID
    membership_id: UUID
    manager_user_id: UUID
    manager_membership_id: UUID
    employee_id: UUID
    other_employee_id: UUID


class FakeContext:
    def __init__(
        self,
        seed: SeededTimekeeping,
        permissions: set[str],
        *,
        manager: bool = False,
    ) -> None:
        self.company = SimpleNamespace(id=seed.company_id)
        self.company.timezone = "America/New_York"
        self.user = SimpleNamespace(
            id=seed.manager_user_id if manager else seed.user_id
        )
        self.membership = SimpleNamespace(
            id=seed.manager_membership_id if manager else seed.membership_id
        )
        self._branch_ids = {seed.branch_id}
        self._permissions = permissions
        self.active_branch = SimpleNamespace(
            id=seed.branch_id, timezone="America/New_York"
        )

    def has_permission(self, code: str) -> bool:
        return code in self._permissions

    def can_access_branch(self, branch_id: UUID) -> bool:
        return branch_id in self._branch_ids


@pytest_asyncio.fixture
async def timekeeping_database() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], SeededTimekeeping]
]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company_id, branch_id, user_id, membership_id = uuid4(), uuid4(), uuid4(), uuid4()
    manager_user_id, manager_membership_id = uuid4(), uuid4()
    employee_id, other_employee_id = uuid4(), uuid4()
    async with factory() as session, session.begin():
        session.add(
            Company(
                id=company_id,
                name="Synthetic Time Company",
                code=f"TIME{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
            )
        )
        session.add(
            Branch(
                id=branch_id,
                company_id=company_id,
                name="Synthetic Time Branch",
                code=f"TB{uuid4().hex[:8].upper()}",
                status="active",
                timezone="America/New_York",
                is_primary=True,
            )
        )
        session.add(
            User(
                id=user_id,
                normalized_email=f"time-{uuid4().hex}@example.test",
                first_name="Time",
                last_name="Worker",
                display_name="Time Worker",
                status="active",
                authorization_version=1,
            )
        )
        session.add(
            User(
                id=manager_user_id,
                normalized_email=f"manager-{uuid4().hex}@example.test",
                first_name="Time",
                last_name="Manager",
                display_name="Time Manager",
                status="active",
                authorization_version=1,
            )
        )
        session.add(
            Membership(
                id=membership_id,
                user_id=user_id,
                company_id=company_id,
                status="active",
                default_branch_id=branch_id,
                has_all_branch_access=False,
                accepted_at=NOW,
            )
        )
        session.add(
            Membership(
                id=manager_membership_id,
                user_id=manager_user_id,
                company_id=company_id,
                status="active",
                default_branch_id=branch_id,
                has_all_branch_access=False,
                accepted_at=NOW,
            )
        )
        await session.flush()
        for value, number in (
            (employee_id, "TIME-001"),
            (other_employee_id, "TIME-002"),
        ):
            session.add(
                Employee(
                    id=value,
                    company_id=company_id,
                    membership_id=membership_id if value == employee_id else None,
                    home_branch_id=branch_id,
                    employee_number=number,
                    first_name="Synthetic",
                    last_name="Employee",
                    display_name=number,
                    employee_type="employee",
                    status="active",
                )
            )
    seed = SeededTimekeeping(
        company_id,
        branch_id,
        user_id,
        membership_id,
        manager_user_id,
        manager_membership_id,
        employee_id,
        other_employee_id,
    )
    try:
        yield factory, seed
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_entry_requires_authority_and_punch_is_employee_owned(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    no_permissions = FakeContext(seed, set())
    manual = RecordManualTime(
        employee_id=seed.employee_id,
        branch_id=seed.branch_id,
        work_date=date(2026, 8, 29),
        timezone="America/New_York",
        start_at=NOW,
        end_at=NOW + timedelta(hours=2),
        approved_duration_minutes=None,
        reason="Missed punch",
    )
    async with factory() as session:
        with pytest.raises(WorkdayAuthorizationError):
            await service.record_manual_time(
                session, context=no_permissions, command=manual  # type: ignore[arg-type]
            )
    punch_context = FakeContext(seed, {TimekeepingPermission.OWN_PUNCH})
    async with factory() as session:
        with pytest.raises(WorkdayAuthorizationError):
            await service.record_punch(
                session,
                context=punch_context,  # type: ignore[arg-type]
                command=RecordPunch(
                    employee_id=seed.other_employee_id,
                    branch_id=seed.branch_id,
                    kind=PunchKind.CLOCK_IN,
                    occurred_at=NOW,
                    timezone="America/New_York",
                ),
            )
    invalid_timezone = RecordManualTime(
        employee_id=seed.employee_id,
        branch_id=seed.branch_id,
        work_date=date(2026, 8, 29),
        timezone="not/a-timezone",
        start_at=NOW,
        end_at=NOW + timedelta(hours=2),
        approved_duration_minutes=None,
        reason="Invalid timezone regression",
    )
    manager_context = FakeContext(
        seed, {TimekeepingPermission.MANUAL_ENTRY}, manager=True
    )
    async with factory() as session:
        with pytest.raises(WorkdayTimeError, match="valid IANA zone"):
            await service.record_manual_time(
                session,
                context=manager_context,  # type: ignore[arg-type]
                command=invalid_timezone,
            )
        with pytest.raises(WorkdayAuthorizationError, match="Branch access"):
            await service.record_manual_time(
                session,
                context=manager_context,  # type: ignore[arg-type]
                command=RecordManualTime(
                    employee_id=seed.employee_id,
                    branch_id=uuid4(),
                    work_date=date(2026, 8, 29),
                    timezone="America/New_York",
                    start_at=NOW,
                    end_at=NOW + timedelta(hours=2),
                    approved_duration_minutes=None,
                    reason="Wrong Branch regression",
                ),
            )


@pytest.mark.asyncio
async def test_mixed_manual_and_punch_time_approval_correction_and_snapshot(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    service = WorkdayTimeService()
    employee_context = FakeContext(
        seed,
        {TimekeepingPermission.OWN_PUNCH, TimekeepingPermission.OWN_READ},
    )
    manager_context = FakeContext(
        seed,
        {
            TimekeepingPermission.MANUAL_ENTRY,
            TimekeepingPermission.CORRECT,
            TimekeepingPermission.APPROVE,
            TimekeepingPermission.ADMIN_READ,
        },
        manager=True,
    )
    async with factory() as session:
        manual = await service.record_manual_time(
            session,
            context=manager_context,  # type: ignore[arg-type]
            command=RecordManualTime(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                work_date=date(2026, 8, 29),
                timezone="America/New_York",
                start_at=NOW,
                end_at=NOW + timedelta(hours=4),
                approved_duration_minutes=None,
                reason="Authorized first-period entry",
            ),
        )
        submitted_manual = await service.submit(
            session,
            context=manager_context,  # type: ignore[arg-type]
            revision_id=manual.id,  # type: ignore[arg-type]
        )
        approved_manual = await service.approve(
            session,
            context=manager_context,  # type: ignore[arg-type]
            revision_id=submitted_manual.id,
        )
        assert (
            approved_manual.provenance
            == TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY.value
        )

        punch_start = NOW + timedelta(days=1)
        await service.record_punch(
            session,
            context=employee_context,  # type: ignore[arg-type]
            command=RecordPunch(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                kind=PunchKind.CLOCK_IN,
                occurred_at=punch_start,
                timezone="America/New_York",
            ),
        )
        with pytest.raises(WorkdayConflictError):
            await service.record_punch(
                session,
                context=employee_context,  # type: ignore[arg-type]
                command=RecordPunch(
                    employee_id=seed.employee_id,
                    branch_id=seed.branch_id,
                    kind=PunchKind.CLOCK_IN,
                    occurred_at=punch_start + timedelta(minutes=1),
                    timezone="America/New_York",
                ),
            )
        clock_out_event, punch_revision = await service.record_punch(
            session,
            context=employee_context,  # type: ignore[arg-type]
            command=RecordPunch(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                kind=PunchKind.CLOCK_OUT,
                occurred_at=punch_start + timedelta(hours=8),
                timezone="America/New_York",
            ),
        )
        assert punch_revision is not None
        submitted_punch = await service.submit(
            session,
            context=employee_context,  # type: ignore[arg-type]
            revision_id=punch_revision.id,  # type: ignore[arg-type]
        )
        self_approver = FakeContext(
            seed,
            {TimekeepingPermission.OWN_PUNCH, TimekeepingPermission.APPROVE},
        )
        with pytest.raises(WorkdayAuthorizationError, match="cannot approve"):
            await service.approve(
                session,
                context=self_approver,  # type: ignore[arg-type]
                revision_id=submitted_punch.id,
            )
        approved_punch = await service.approve(
            session,
            context=manager_context,  # type: ignore[arg-type]
            revision_id=submitted_punch.id,
        )
        assert approved_punch.provenance == TimeEntryProvenance.EMPLOYEE_PUNCH.value

        await service.record_manual_time(
            session,
            context=manager_context,  # type: ignore[arg-type]
            command=RecordManualTime(
                employee_id=seed.employee_id,
                branch_id=seed.branch_id,
                work_date=date(2026, 8, 31),
                timezone="America/New_York",
                start_at=NOW + timedelta(days=2),
                end_at=NOW + timedelta(days=2, hours=1),
                approved_duration_minutes=None,
                reason="Unsubmitted synthetic entry",
            ),
        )

        period = await service.create_pay_period(
            session,
            context=manager_context,  # type: ignore[arg-type]
            command=CreatePayPeriod(
                period_start=date(2026, 8, 29),
                period_end=date(2026, 9, 4),
                processing_date=date(2026, 9, 10),
                payday=date(2026, 9, 11),
                timezone="America/New_York",
                schedule_definition_id="synthetic.all-county.weekly-held-back",
                schedule_version=1,
            ),
        )
        first = await service.seal_payroll_input(
            session,
            context=manager_context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        replay = await service.seal_payroll_input(
            session,
            context=manager_context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        assert first.snapshot_digest == replay.snapshot_digest
        assert first.total_approved_minutes == 720
        assert len(first.approved_entries) == 2
        assert {value.provenance for value in first.approved_entries} == {
            TimeEntryProvenance.EMPLOYEE_PUNCH,
            TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY,
        }
        economics = to_economics_workday_time(first.approved_entries[0])
        assert economics.workday_time_id

        corrected = await service.correct(
            session,
            context=manager_context,  # type: ignore[arg-type]
            command=CorrectTimeEntry(
                revision_id=approved_manual.id,
                start_at=NOW,
                end_at=NOW + timedelta(hours=5),
                approved_duration_minutes=None,
                reason="Manager-approved missed-punch correction",
            ),
        )
        resubmitted = await service.submit(
            session,
            context=manager_context,  # type: ignore[arg-type]
            revision_id=corrected.id,  # type: ignore[arg-type]
        )
        await service.approve(
            session,
            context=manager_context,  # type: ignore[arg-type]
            revision_id=resubmitted.id,  # type: ignore[arg-type]
        )
        changed = await service.seal_payroll_input(
            session,
            context=manager_context,  # type: ignore[arg-type]
            employee_id=seed.employee_id,
            pay_period=period,
        )
        assert changed.snapshot_digest != first.snapshot_digest
        assert changed.total_approved_minutes == 780
        assert approved_manual.id in changed.approved_entries[0].correction_lineage

        immutable_attacks = (
            update(PayPeriod).where(PayPeriod.id == period.id).values(timezone="UTC"),
            delete(PayPeriod).where(PayPeriod.id == period.id),
            update(WorkdayPunchEvent)
            .where(WorkdayPunchEvent.id == clock_out_event.id)
            .values(event_digest="0" * 64),
            delete(WorkdayPunchEvent).where(WorkdayPunchEvent.id == clock_out_event.id),
            update(WorkdayTimeEntryRevision)
            .where(WorkdayTimeEntryRevision.id == approved_manual.id)
            .values(evidence_digest="0" * 64),
            delete(WorkdayTimeEntryRevision).where(
                WorkdayTimeEntryRevision.id == approved_manual.id
            ),
            update(PayrollTimeInputRecord)
            .where(PayrollTimeInputRecord.snapshot_digest == first.snapshot_digest)
            .values(snapshot_digest="0" * 64),
            delete(PayrollTimeInputRecord).where(
                PayrollTimeInputRecord.snapshot_digest == first.snapshot_digest
            ),
        )
        for attack in immutable_attacks:
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(attack)


@pytest.mark.asyncio
async def test_phone_safe_api_manual_first_idempotency_and_payroll_snapshot(
    timekeeping_database: tuple[async_sessionmaker[AsyncSession], SeededTimekeeping],
) -> None:
    factory, seed = timekeeping_database
    employee_context = FakeContext(
        seed,
        {
            TimekeepingPermission.OWN_PUNCH,
            TimekeepingPermission.OWN_READ,
            TimekeepingPermission.APPROVE,
        },
    )
    manager_context = FakeContext(
        seed,
        {
            TimekeepingPermission.MANUAL_ENTRY,
            TimekeepingPermission.CORRECT,
            TimekeepingPermission.APPROVE,
            TimekeepingPermission.ADMIN_READ,
        },
        manager=True,
    )
    today = datetime.now(timezone.utc).astimezone().date()
    async with factory() as session:
        period = await WorkdayTimeService().create_pay_period(
            session,
            context=manager_context,  # type: ignore[arg-type]
            command=CreatePayPeriod(
                period_start=today - timedelta(days=1),
                period_end=today + timedelta(days=5),
                processing_date=today + timedelta(days=6),
                payday=today + timedelta(days=7),
                timezone="America/New_York",
                schedule_definition_id="synthetic.phone-first.weekly",
                schedule_version=1,
            ),
        )

    selected_context: dict[str, FakeContext] = {"value": manager_context}

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    async def context_override() -> FakeContext:
        return selected_context["value"]

    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_authorization_context] = context_override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            manual_payload = {
                "employee_id": str(seed.employee_id),
                "work_date": (today - timedelta(days=1)).isoformat(),
                "timezone": "America/New_York",
                "start_at": (NOW - timedelta(days=1)).isoformat(),
                "end_at": (NOW - timedelta(days=1) + timedelta(hours=2)).isoformat(),
                "reason": "Manager-entered time before employee login",
            }
            manual = await client.post(
                "/api/v1/timekeeping/entries/manual",
                headers={"Idempotency-Key": "manual-first-day"},
                json=manual_payload,
            )
            assert manual.status_code == 200, manual.text
            manual_retry = await client.post(
                "/api/v1/timekeeping/entries/manual",
                headers={"Idempotency-Key": "manual-first-day"},
                json=manual_payload,
            )
            assert manual_retry.json()["revision_id"] == manual.json()["revision_id"]

            submitted_manual = await client.post(
                f"/api/v1/timekeeping/entries/{manual.json()['revision_id']}/submit"
            )
            assert submitted_manual.status_code == 200

            selected_context["value"] = employee_context
            before = datetime.now(timezone.utc)
            clock_in = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "phone-clock-in"},
                json={"action": "clock_in", "device_reference": "phone-session"},
            )
            after = datetime.now(timezone.utc)
            assert clock_in.status_code == 200, clock_in.text
            occurred_at = datetime.fromisoformat(clock_in.json()["occurred_at"])
            assert before <= occurred_at <= after
            client_identity_attempt = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "client-identity-attempt"},
                json={
                    "action": "clock_out",
                    "employee_id": str(seed.other_employee_id),
                    "occurred_at": NOW.isoformat(),
                },
            )
            assert client_identity_attempt.status_code == 422
            duplicate = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "phone-clock-in"},
                json={"action": "clock_in", "device_reference": "phone-session"},
            )
            assert duplicate.status_code == 200
            assert duplicate.json()["punch_id"] == clock_in.json()["punch_id"]
            impossible = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "second-clock-in"},
                json={"action": "clock_in"},
            )
            assert impossible.status_code == 409
            reused_key = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "phone-clock-in"},
                json={"action": "clock_out", "device_reference": "phone-session"},
            )
            assert reused_key.status_code == 409

            clock_out = await client.post(
                "/api/v1/timekeeping/me/punches",
                headers={"Idempotency-Key": "phone-clock-out"},
                json={"action": "clock_out", "device_reference": "phone-session"},
            )
            assert clock_out.status_code == 200, clock_out.text
            punched_revision = clock_out.json()["completed_entry"]["revision_id"]
            submitted_punch = await client.post(
                f"/api/v1/timekeeping/entries/{punched_revision}/submit"
            )
            assert submitted_punch.status_code == 200
            self_approval = await client.post(
                f"/api/v1/timekeeping/entries/{submitted_punch.json()['revision_id']}/approve"
            )
            assert self_approval.status_code == 403

            timecard = await client.get("/api/v1/timekeeping/me/timecard")
            assert timecard.status_code == 200
            assert timecard.json()["employee_id"] == str(seed.employee_id)
            assert "compensation" not in timecard.text.lower()
            assert "rate" not in timecard.text.lower()
            assert {item["provenance"] for item in timecard.json()["entries"]} == {
                "authorized_manual_entry",
                "employee_punch",
            }

            selected_context["value"] = manager_context
            approved_revision_ids: list[str] = []
            for revision_id in (
                submitted_manual.json()["revision_id"],
                submitted_punch.json()["revision_id"],
            ):
                approved = await client.post(
                    f"/api/v1/timekeeping/entries/{revision_id}/approve"
                )
                assert approved.status_code == 200, approved.text
                approved_revision_ids.append(approved.json()["revision_id"])
            snapshot = await client.post(
                f"/api/v1/timekeeping/pay-periods/{period.id}/employees/"
                f"{seed.employee_id}/payroll-time-input"
            )
            assert snapshot.status_code == 200, snapshot.text
            assert set(snapshot.json()["approved_revision_ids"]) == set(
                approved_revision_ids
            )
            replay = await client.post(
                f"/api/v1/timekeeping/pay-periods/{period.id}/employees/"
                f"{seed.employee_id}/payroll-time-input"
            )
            assert replay.json()["snapshot_digest"] == snapshot.json()["snapshot_digest"]

            foreign_context = FakeContext(
                seed, {TimekeepingPermission.OWN_PUNCH, TimekeepingPermission.OWN_READ}
            )
            foreign_context.company = SimpleNamespace(
                id=uuid4(), timezone="America/New_York"
            )
            selected_context["value"] = foreign_context
            foreign = await client.get("/api/v1/timekeeping/me/timecard")
            assert foreign.status_code == 403
    finally:
        app.dependency_overrides.clear()
