from datetime import date
from uuid import uuid4

import pytest
from app.accounting.models import Journal
from app.payroll.accounting_finalization import PayrollAccountingFinalizationService
from app.payroll.accounting_posting import (
    PayrollAccountingComponent,
    PayrollRecognitionEvent,
)
from app.payroll.contracts import PayrollConflictError
from app.payroll.permissions import PayrollPermission
from app.platform.permissions.codes import AccountingPermission
from app.platform.users.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.payroll.test_accounting_posting_authority import accounting_foundation
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database


@pytest.mark.asyncio
async def test_synthetic_governed_posting_is_single_consumption(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        components = (
            PayrollAccountingComponent.GROSS_WAGES,
            PayrollAccountingComponent.EMPLOYEE_TAX_WITHHOLDING,
            PayrollAccountingComponent.EMPLOYEE_DEDUCTION_PAYABLE,
            PayrollAccountingComponent.NET_PAY_PAYABLE,
            PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE,
            PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_LIABILITY,
        )
        adapter, _, period = await accounting_foundation(
            session, values, components, PayrollRecognitionEvent.PAYROLL_ACCRUAL
        )
        preparer = FakeContext(
            values["company_id"],
            values["actor_id"],
            {PayrollPermission.ACCOUNTING_PREPARE, AccountingPermission.JOURNAL_PREPARE},
        )
        approver = FakeContext(
            values["company_id"], values["reviewer_id"], {AccountingPermission.FINANCE_APPROVE}
        )
        poster_id = uuid4()
        session.add(
            User(
                id=poster_id,
                normalized_email=f"poster-{uuid4().hex}@example.test",
                first_name="Synthetic",
                last_name="Poster",
                display_name="Synthetic Poster",
                status="active",
                authorization_version=1,
            )
        )
        await session.commit()
        poster = FakeContext(values["company_id"], poster_id, {AccountingPermission.JOURNAL_POST})
        candidate = await adapter.prepare_accrual(
            session,
            context=preparer,
            payroll_run_id=run.id,
            effective_date=date(2026, 9, 4),
            period_id=period.id,
        )
        service = PayrollAccountingFinalizationService()
        first = await service.post_candidate(
            session,
            candidate=candidate,
            period_id=period.id,
            preparer=preparer,
            approver=approver,
            poster=poster,
        )
        replay = await service.post_candidate(
            session,
            candidate=candidate,
            period_id=period.id,
            preparer=preparer,
            approver=approver,
            poster=poster,
        )
        assert replay.journal_id == first.journal_id
        assert await session.scalar(select(func.count(Journal.id)).where(Journal.company_id == values["company_id"])) == 1


@pytest.mark.asyncio
async def test_candidate_persistence_is_company_isolated(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        components = (
            PayrollAccountingComponent.GROSS_WAGES,
            PayrollAccountingComponent.EMPLOYEE_TAX_WITHHOLDING,
            PayrollAccountingComponent.EMPLOYEE_DEDUCTION_PAYABLE,
            PayrollAccountingComponent.NET_PAY_PAYABLE,
            PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE,
            PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_LIABILITY,
        )
        adapter, prepare, period = await accounting_foundation(
            session, values, components, PayrollRecognitionEvent.PAYROLL_ACCRUAL
        )
        candidate = await adapter.prepare_accrual(
            session, context=prepare, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=period.id
        )
        other = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.ACCOUNTING_PREPARE})
        with pytest.raises(PayrollConflictError, match="cross-Company"):
            await PayrollAccountingFinalizationService().persist_candidate(session, context=other, candidate=candidate)
