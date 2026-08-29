from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.accounting.errors import AccountingConflict, AccountingValidation
from app.accounting.models import Account, AccountingPeriod, ChartVersion
from app.accounting.posting.contracts import PostingSide
from app.accounting.posting.rules import PostingRuleRegistry
from app.accounting.posting.service import AutomatedPostingService
from app.customers.models import Customer  # noqa: F401
from app.payroll.accounting_posting import (
    DraftPayrollAccountingMapping,
    DraftPayrollAccountingPolicy,
    PayrollAccountingComponent,
    PayrollAccountingPostingService,
    PayrollRecognitionEvent,
)
from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.models import PayrollPaymentExecutionItemRecord
from app.payroll.payment_execution import (
    InstructionExecutionState,
    SettlementItemEvidence,
    SyntheticPaymentExecutionProvider,
)
from app.payroll.permissions import PayrollPermission
from app.scheduling.models import Appointment  # noqa: F401
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_execution_authority import (
    authorized_execution,
    execution_contexts,
)
from tests.payroll.test_payment_release_authority import approved_run

finalization_database = _database
NOW = datetime(2026, 9, 10, 20, tzinfo=timezone.utc)


def authority_contexts(values: dict[str, object]) -> tuple[Any, Any, Any]:
    manage = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.ACCOUNTING_POLICY_MANAGE, PayrollPermission.ACCOUNTING_MAPPING_MANAGE})
    approve = FakeContext(values["company_id"], values["reviewer_id"], {PayrollPermission.ACCOUNTING_POLICY_APPROVE, PayrollPermission.ACCOUNTING_MAPPING_APPROVE})
    prepare = FakeContext(values["company_id"], values["actor_id"], {PayrollPermission.ACCOUNTING_PREPARE})
    return manage, approve, prepare


async def accounting_foundation(session: AsyncSession, values: dict[str, object], components: tuple[PayrollAccountingComponent, ...], event: PayrollRecognitionEvent):
    chart = ChartVersion(company_id=values["company_id"], version=1, name="Synthetic Payroll Chart", currency="USD", accounting_basis="accrual", source_checksum="a" * 64, effective_at=NOW, is_active=True, approved_by_user_id=values["reviewer_id"])
    session.add(chart)
    await session.flush()
    period = AccountingPeriod(company_id=values["company_id"], name="Synthetic September", start_date=date(2026, 9, 1), end_date=date(2026, 9, 30), status="open", created_by_user_id=values["actor_id"])
    session.add(period)
    accounts: dict[PayrollAccountingComponent, Account] = {}
    for ordinal, component in enumerate(components, 1):
        account = Account(company_id=values["company_id"], chart_version_id=chart.id, code=f"SYN-{ordinal:03}", name=f"Synthetic {component.value}", classification="expense" if component in {PayrollAccountingComponent.GROSS_WAGES, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE} else "liability", normal_balance="debit" if component in {PayrollAccountingComponent.GROSS_WAGES, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE, PayrollAccountingComponent.NET_PAY_LIABILITY_SETTLEMENT} else "credit", status="active", effective_from=date(2026, 1, 1))
        session.add(account)
        accounts[component] = account
    await session.commit()
    service = PayrollAccountingPostingService()
    manage, approve, prepare = authority_contexts(values)
    policy = await service.create_policy(session, context=manage, draft=DraftPayrollAccountingPolicy(1, event, "USD", date(2026, 1, 1), None, canonical_digest({"synthetic-policy": event.value})))
    await service.approve_policy(session, context=approve, policy_id=policy.id)
    debit_components = {PayrollAccountingComponent.GROSS_WAGES, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE, PayrollAccountingComponent.NET_PAY_LIABILITY_SETTLEMENT}
    for component in components:
        mapping = await service.create_mapping(session, context=manage, draft=DraftPayrollAccountingMapping(1, event, component, PostingSide.DEBIT if component in debit_components else PostingSide.CREDIT, accounts[component].id, "USD", date(2026, 1, 1), None, canonical_digest({"synthetic-mapping": component.value})))
        await service.approve_mapping(session, context=approve, mapping_id=mapping.id)
    return service, prepare, period


@pytest.mark.asyncio
async def test_approved_run_projects_balanced_native_posting_fact(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        components = (PayrollAccountingComponent.GROSS_WAGES, PayrollAccountingComponent.EMPLOYEE_TAX_WITHHOLDING, PayrollAccountingComponent.EMPLOYEE_DEDUCTION_PAYABLE, PayrollAccountingComponent.NET_PAY_PAYABLE, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_LIABILITY)
        service, prepare, period = await accounting_foundation(session, values, components, PayrollRecognitionEvent.PAYROLL_ACCRUAL)
        candidate = await service.prepare_accrual(session, context=prepare, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=period.id)
        candidate.verify()
        registry = PostingRuleRegistry((candidate.posting_rule,))
        data = AutomatedPostingService(rules=registry)._journal_create(candidate.fact, registry.resolve(candidate.fact), period.id)
        assert sum(line.debit for line in data.lines) == sum(line.credit for line in data.lines)
        replay = await service.prepare_accrual(session, context=prepare, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=period.id)
        assert replay.candidate_identity == candidate.candidate_identity
        assert PayrollAccountingComponent.GROSS_WAGES.value in candidate.fact.components


@pytest.mark.asyncio
async def test_policy_mapping_company_currency_and_period_fail_closed(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        _, _, prepare = authority_contexts(values)
        service = PayrollAccountingPostingService()
        with pytest.raises(AccountingValidation, match="period"):
            await service.prepare_accrual(session, context=prepare, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=uuid4())
        components = (PayrollAccountingComponent.GROSS_WAGES, PayrollAccountingComponent.EMPLOYEE_TAX_WITHHOLDING, PayrollAccountingComponent.EMPLOYEE_DEDUCTION_PAYABLE, PayrollAccountingComponent.NET_PAY_PAYABLE, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_EXPENSE, PayrollAccountingComponent.EMPLOYER_CONTRIBUTION_LIABILITY)
        service, prepare, period = await accounting_foundation(session, values, components, PayrollRecognitionEvent.PAYROLL_ACCRUAL)
        period.status = "closed"
        await session.commit()
        with pytest.raises(AccountingConflict, match="period"):
            await service.prepare_accrual(session, context=prepare, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=period.id)
        other = FakeContext(values["other_company_id"], values["actor_id"], {PayrollPermission.ACCOUNTING_PREPARE})
        with pytest.raises(PayrollConflictError, match="approved Payroll run"):
            await service.prepare_accrual(session, context=other, payroll_run_id=run.id, effective_date=date(2026, 9, 4), period_id=period.id)


@pytest.mark.asyncio
async def test_only_explicit_settled_instructions_project_wage_settlement(finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]]) -> None:
    factory, values = finalization_database
    async with factory() as session:
        execution_service, _, _, execution = await authorized_execution(session, values)
        authorize, reconcile, _ = execution_contexts(values)
        await execution_service.submit(session, context=authorize, execution_id=execution.id, provider=SyntheticPaymentExecutionProvider(environment="test"))
        item = (
            await session.execute(
                select(PayrollPaymentExecutionItemRecord).where(
                    PayrollPaymentExecutionItemRecord.execution_id == execution.id
                )
            )
        ).scalar_one()
        reference = "synthetic-settlement"
        digest = canonical_digest({"instruction_id": str(item.instruction_id), "state": "settled", "provider_safe_reference": reference})
        await execution_service.record_settlement(session, context=reconcile, execution_id=execution.id, outcomes=(SettlementItemEvidence(item.instruction_id, InstructionExecutionState.SETTLED, reference, digest),), occurred_at=NOW)
        components = (PayrollAccountingComponent.NET_PAY_LIABILITY_SETTLEMENT, PayrollAccountingComponent.WAGE_SETTLEMENT)
        service, prepare, period = await accounting_foundation(session, values, components, PayrollRecognitionEvent.WAGE_SETTLEMENT)
        candidate = await service.prepare_wage_settlement(session, context=prepare, execution_id=execution.id, effective_date=date(2026, 9, 10), period_id=period.id)
        assert set(candidate.fact.components) == {item.value for item in components}
        assert PayrollAccountingComponent.GROSS_WAGES.value not in candidate.fact.components
