from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.models import PayrollPayStatementArtifactRecord
from app.payroll.paystatement import PayrollPayStatementService
from app.payroll.paystatement_experience import (
    PayrollPayStatementExperienceService,
    ProtectedStatementStorage,
)
from app.payroll.permissions import PayrollPermission
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


@pytest.mark.asyncio
async def test_render_replay_storage_binding_and_own_isolation(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
    tmp_path: Path,
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        employee = await session.scalar(
            select(Employee).where(Employee.id == values["employee_id"])
        )
        assert employee is not None
        membership = Membership(
            user_id=values["actor_id"],
            company_id=values["company_id"],
            status="active",
            default_branch_id=employee.home_branch_id,
            has_all_branch_access=False,
        )
        session.add(membership)
        await session.flush()
        employee.membership_id = membership.id
        await session.commit()
        manage = FakeContext(
            values["company_id"],
            values["actor_id"],
            {PayrollPermission.STATEMENT_MANAGE},
        )
        statement_service = PayrollPayStatementService()
        statement = await statement_service.create(
            session, context=manage, run_id=run.id, employee_id=employee.id
        )
        await statement_service.issue(
            session, context=manage, statement_id=statement.id
        )
        experience = PayrollPayStatementExperienceService(
            ProtectedStatementStorage(tmp_path.resolve())
        )
        artifact = await experience.render(
            session, context=manage, statement_id=statement.id
        )
        replay = await experience.render(
            session, context=manage, statement_id=statement.id
        )
        assert replay.id == artifact.id
        stored_file = next(tmp_path.rglob("psa-*"))
        assert stored_file.stat().st_mode & 0o777 == 0o600
        assert str(values["company_id"]) in stored_file.parts
        assert str(employee.id) in stored_file.parts

        own = FakeContext(
            values["company_id"],
            values["actor_id"],
            {PayrollPermission.STATEMENT_OWN_READ},
        )
        own.membership = SimpleNamespace(id=membership.id)
        retrieved, content = await experience.own_artifact(
            session, context=own, statement_id=statement.id
        )
        assert retrieved.digest == artifact.digest
        assert b"Year-to-date totals are unavailable" in content
        assert b"Employer" not in content
        assert str(tmp_path).encode() not in content

        delivery = await experience.prepare_delivery(
            session,
            context=manage,
            statement_id=statement.id,
            channel="email_link",
            recipient_reference="synthetic-recipient@example.invalid",
        )
        outbox = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.correlation_id == delivery.id
            )
        )
        assert outbox is not None
        assert outbox.payload == {
            "message": "A new pay statement is available.",
            "link": f"/employee/pay-statements/{statement.id}",
            "pay_period_id": str(statement.pay_period_id),
        }
        assert "net_pay" not in str(outbox.payload)
        assert "token" not in str(outbox.payload["link"])

        artifact_record = await session.scalar(
            select(PayrollPayStatementArtifactRecord).where(
                PayrollPayStatementArtifactRecord.id == artifact.id
            )
        )
        assert artifact_record is not None
        stored_file.write_bytes(b"tampered")
        with pytest.raises(PayrollConflictError, match="failed verification"):
            await experience.own_artifact(
                session, context=own, statement_id=statement.id
            )

        denied = FakeContext(
            values["company_id"],
            values["reviewer_id"],
            {PayrollPermission.STATEMENT_OWN_READ},
        )
        denied.membership = SimpleNamespace(id=uuid4())
        with pytest.raises(PayrollAuthorizationError):
            await experience.own_artifact(
                session, context=denied, statement_id=statement.id
            )


def test_storage_rejects_nonopaque_and_relative_locations(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProtectedStatementStorage(Path("relative"))
    storage = ProtectedStatementStorage(tmp_path.resolve())
    with pytest.raises(PayrollConflictError):
        storage.put(uuid4(), uuid4(), "../public", b"unsafe")


@pytest.mark.asyncio
async def test_storage_failure_creates_no_artifact_authority(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
    tmp_path: Path,
) -> None:
    factory, values = finalization_database

    class UnavailableStorage(ProtectedStatementStorage):
        def put(
            self, company_id, employee_id, reference: str, content: bytes
        ) -> None:
            raise OSError("synthetic protected storage unavailable")

    async with factory() as session:
        run, _ = await approved_run(session, values)
        employee = await session.scalar(
            select(Employee).where(Employee.id == values["employee_id"])
        )
        assert employee is not None
        context = FakeContext(
            values["company_id"],
            values["actor_id"],
            {PayrollPermission.STATEMENT_MANAGE},
        )
        statement = await PayrollPayStatementService().create(
            session, context=context, run_id=run.id, employee_id=employee.id
        )
        await PayrollPayStatementService().issue(
            session, context=context, statement_id=statement.id
        )
        service = PayrollPayStatementExperienceService(
            UnavailableStorage(tmp_path.resolve())
        )
        artifact_count_before = await session.scalar(
            select(func.count()).select_from(PayrollPayStatementArtifactRecord)
        )

        with pytest.raises(OSError, match="storage unavailable"):
            await service.render(session, context=context, statement_id=statement.id)

        assert (
            await session.scalar(
                select(func.count()).select_from(PayrollPayStatementArtifactRecord)
            )
            == artifact_count_before
        )
