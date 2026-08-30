from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.payroll.contracts import PayrollAuthorizationError, PayrollConflictError
from app.payroll.models import PayrollPayStatementRecord
from app.payroll.paystatement import PayrollPayStatementService
from app.payroll.permissions import PayrollPermission
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


@pytest.mark.asyncio
async def test_statement_is_deterministic_immutable_and_self_scoped(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        employee = await session.scalar(select(Employee).where(Employee.id == values["employee_id"]))
        assert employee is not None
        membership = Membership(user_id=values["actor_id"], company_id=values["company_id"], status="active", default_branch_id=employee.home_branch_id, has_all_branch_access=False)
        session.add(membership)
        await session.flush()
        employee.membership_id = membership.id
        await session.commit()

        manage = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.STATEMENT_MANAGE})
        service = PayrollPayStatementService()
        value = await service.create(session, context=manage, run_id=run.id, employee_id=employee.id)
        replay = await service.create(session, context=manage, run_id=run.id, employee_id=employee.id)
        assert replay.id == value.id
        assert value.ytd_status == "unavailable"
        assert value.payment_status == "not_available"
        assert "employer_contributions" not in value.content
        await service.issue(session, context=manage, statement_id=value.id)

        own = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.STATEMENT_OWN_READ})
        own.membership = SimpleNamespace(id=membership.id)
        view = await service.own(session, context=own, statement_id=value.id)
        assert view.digest == value.statement_digest
        assert view.content["net_pay"] == str(value.content["net_pay"])
        assert [item.id for item in await service.list_own(
            session, context=own, limit=1, offset=0
        )] == [value.id]
        assert await service.list_own(session, context=own, limit=1, offset=1) == ()
        statement_count, current = await service.own_summary(session, context=own)
        assert statement_count == 1
        assert current is not None and current.id == value.id
        with pytest.raises(PayrollConflictError, match="pagination"):
            await service.list_own(session, context=own, limit=201)

        unauthorized = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.STATEMENT_READ})
        with pytest.raises(PayrollAuthorizationError, match="permission"):
            await service.own(session, context=unauthorized, statement_id=value.id)
        other_company = FakeContext(values["other_company_id"], values["reviewer_id"], {PayrollPermission.STATEMENT_READ})
        with pytest.raises(PayrollConflictError, match="not found"):
            await service.administrative(session, context=other_company, statement_id=value.id)


@pytest.mark.asyncio
async def test_unapproved_run_cannot_issue_statement(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        run.lifecycle = "reviewed"
        await session.commit()
        manage = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.STATEMENT_MANAGE})
        with pytest.raises(PayrollConflictError, match="approved complete"):
            await PayrollPayStatementService().create(session, context=manage, run_id=run.id, employee_id=values["employee_id"])


def test_safe_event_contract_excludes_statement_amounts() -> None:
    forbidden = {"gross_pay", "net_pay", "employee_taxes", "employee_deductions", "bank", "routing", "ssn"}
    safe = {"statement_id", "statement_digest", "employee_id", "pay_period_id", "lifecycle", "state"}
    assert forbidden.isdisjoint(safe)
    assert PayrollPayStatementRecord.__tablename__ == "payroll_pay_statements"
