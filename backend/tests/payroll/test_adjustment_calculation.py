from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customers.models import Customer  # noqa: F401
from app.payroll.adjustment_calculation import (
    AdjustmentCalculationError,
    AdjustmentConsequenceType,
    AuthorizedDeltaRuleProvider,
    PayrollAdjustmentCalculationService,
    RecognitionEffect,
    RuleEnvironment,
    SyntheticTaxAdjustmentProvider,
)
from app.payroll.adjustments import (
    AdjustmentReviewDecision,
    DraftPayrollAdjustment,
    EconomicDelta,
    PayrollAdjustmentService,
    PayrollCorrectionType,
)
from app.payroll.contracts import PayrollAuthorizationError, canonical_digest
from app.payroll.permissions import PayrollPermission
from app.scheduling.models import Appointment  # noqa: F401
from tests.payroll.test_adjustment_authority import draft
from tests.payroll.test_gross_pay_finalization import FakeContext
from tests.payroll.test_gross_pay_finalization import finalization_database as _database
from tests.payroll.test_payment_execution_authority import authorized_execution
from tests.payroll.test_payment_release_authority import approved_run
from tests.payroll.test_payroll_run_finalization import approved_tax_result

finalization_database = _database


async def approved_adjustment(
    session: AsyncSession,
    values: dict[str, object],
    command: DraftPayrollAdjustment,
):  # type: ignore[no-untyped-def]
    manage: Any = FakeContext(
        values["company_id"], values["actor_id"], {PayrollPermission.ADJUSTMENT_MANAGE}
    )
    review: Any = FakeContext(
        values["company_id"], values["reviewer_id"], {PayrollPermission.ADJUSTMENT_REVIEW}
    )
    approve: Any = FakeContext(
        values["company_id"], values["reviewer_id"], {PayrollPermission.ADJUSTMENT_APPROVE}
    )
    service = PayrollAdjustmentService()
    value = await service.create(session, context=manage, draft=command)
    await service.initiate_review(
        session, context=review, adjustment_id=value.id, reason_code="synthetic"
    )
    await service.decide_review(
        session,
        context=review,
        adjustment_id=value.id,
        decision=AdjustmentReviewDecision.ACCEPTED,
        reason_code="synthetic",
    )
    await service.approve(
        session, context=approve, adjustment_id=value.id, reason_code="synthetic"
    )
    await session.refresh(value)
    return value


def calculation_context(values: dict[str, object], company_id: object | None = None) -> Any:
    return FakeContext(
        company_id or values["company_id"],
        values["actor_id"],
        {PayrollPermission.ADJUSTMENT_CALCULATE},
    )


@pytest.mark.asyncio
async def test_retroactive_and_off_cycle_are_deterministic_and_preserve_run(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        original = (run.run_digest, run.lifecycle, run.aggregate_gross)
        authority = await approved_adjustment(session, values, draft(run))
        calculator = PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.TEST
        )
        first = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=authority.id,
            provider=AuthorizedDeltaRuleProvider(),
        )
        replay = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=authority.id,
            provider=AuthorizedDeltaRuleProvider(),
        )
        assert first.result_identity == replay.result_identity
        assert first.calculation_digest == replay.calculation_digest
        assert first.calculated_at != replay.calculated_at
        assert first.components[0].delta == Decimal("25.00")
        assert first.consequences == (
            AdjustmentConsequenceType.SUCCESSOR_PAYROLL_REQUIRED,
        )
        changed_rule = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=authority.id,
            provider=AuthorizedDeltaRuleProvider(provider_version="authorized-delta.v2"),
        )
        assert changed_rule.calculation_digest != first.calculation_digest
        await session.refresh(run)
        assert (run.run_digest, run.lifecycle, run.aggregate_gross) == original

        off_cycle_command = draft(run, PayrollCorrectionType.OFF_CYCLE_PAYROLL)
        off_cycle = await approved_adjustment(session, values, off_cycle_command)
        result = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=off_cycle.id,
            provider=AuthorizedDeltaRuleProvider(),
        )
        assert result.original_pay_period_id == run.pay_period_id
        assert result.correction_pay_period_id != run.pay_period_id
        assert result.consequences == (
            AdjustmentConsequenceType.OFF_CYCLE_PAYROLL_REQUIRED,
        )


@pytest.mark.asyncio
async def test_tax_and_deduction_corrections_bind_original_results_and_test_provider(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        tax, _ = await approved_tax_result(session, values)
        tax_pay_period_id = tax.pay_period_id
        base = DraftPayrollAdjustment(
            classification=PayrollCorrectionType.TAX_CORRECTION,
            reason_code="synthetic_tax_correction",
            source_type="tax_result",
            source_id=tax.id,
            source_digest=tax.calculation_digest,
            currency=tax.currency,
            effective_date=date(2026, 9, 18),
            evidence_digest=canonical_digest({"synthetic-tax": True}),
            delta_components=(
                EconomicDelta("employee_tax_withholding", Decimal("-3.25")),
            ),
            employee_id=tax.employee_id,
            original_pay_period_id=tax_pay_period_id,
        )
        authority = await approved_adjustment(session, values, base)
        calculator = PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.TEST
        )
        result = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=authority.id,
            provider=SyntheticTaxAdjustmentProvider(),
        )
        assert result.source_id == tax.id
        assert result.components[0].recognition_effect is RecognitionEffect.TAX_LIABILITY_DELTA
        assert result.consequences == (
            AdjustmentConsequenceType.TAX_SUCCESSOR_REQUIRED,
        )
        production = PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.PRODUCTION
        )
        with pytest.raises(AdjustmentCalculationError, match="synthetic"):
            await production.calculate(
                session,
                context=calculation_context(values),
                adjustment_id=authority.id,
                provider=SyntheticTaxAdjustmentProvider(),
            )

        deduction = replace(
            base,
            classification=PayrollCorrectionType.DEDUCTION_CORRECTION,
            reason_code="synthetic_deduction_correction",
            evidence_digest=canonical_digest({"synthetic-deduction": True}),
            delta_components=(EconomicDelta("employee_deduction", Decimal("4.00")),),
        )
        deduction_authority = await approved_adjustment(session, values, deduction)
        deduction_result = await calculator.calculate(
            session,
            context=calculation_context(values),
            adjustment_id=deduction_authority.id,
            provider=AuthorizedDeltaRuleProvider(),
        )
        assert deduction_result.source_id == tax.id
        assert deduction_result.components[0].recognition_effect is RecognitionEffect.DEDUCTION_LIABILITY_DELTA


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("classification", "expected", "effect"),
    (
        (
            PayrollCorrectionType.PAYMENT_RETURN,
            AdjustmentConsequenceType.PAYMENT_RECOVERY_REQUIRED,
            RecognitionEffect.SETTLEMENT_DELTA,
        ),
        (
            PayrollCorrectionType.PAYMENT_REJECTION,
            AdjustmentConsequenceType.PAYMENT_REISSUE_REQUIRED,
            RecognitionEffect.NO_POSTING_EFFECT,
        ),
        (
            PayrollCorrectionType.PAYMENT_REVERSAL,
            AdjustmentConsequenceType.PAYMENT_RECOVERY_REQUIRED,
            RecognitionEffect.SETTLEMENT_DELTA,
        ),
    ),
)
async def test_payment_corrections_never_recreate_wage_expense(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
    classification: PayrollCorrectionType,
    expected: AdjustmentConsequenceType,
    effect: RecognitionEffect,
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        _, _, _, execution = await authorized_execution(session, values)
        command = DraftPayrollAdjustment(
            classification=classification,
            reason_code="synthetic_payment_correction",
            source_type="payment_execution",
            source_id=execution.id,
            source_digest=execution.execution_digest,
            currency=execution.currency,
            effective_date=date(2026, 9, 19),
            evidence_digest=canonical_digest(
                {"synthetic-payment": classification.value}
            ),
            delta_components=(EconomicDelta("wage_settlement", Decimal("-100.00")),),
        )
        authority = await approved_adjustment(session, values, command)
        result = await PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.TEST
        ).calculate(
            session,
            context=calculation_context(values),
            adjustment_id=authority.id,
            provider=AuthorizedDeltaRuleProvider(),
        )
        assert result.consequences == (expected,)
        assert result.components[0].recognition_effect is effect
        assert all(item.component != "gross_wages" for item in result.components)


@pytest.mark.asyncio
async def test_scope_permission_integrity_and_invalid_delta_fail_closed(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        run, _ = await approved_run(session, values)
        authority = await approved_adjustment(session, values, draft(run))
        calculator = PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.TEST
        )
        denied: Any = FakeContext(values["company_id"], values["actor_id"], set())
        with pytest.raises(PayrollAuthorizationError):
            await calculator.calculate(
                session,
                context=denied,
                adjustment_id=authority.id,
                provider=AuthorizedDeltaRuleProvider(),
            )
        with pytest.raises(AdjustmentCalculationError, match="approved"):
            await calculator.calculate(
                session,
                context=calculation_context(values, values["other_company_id"]),
                adjustment_id=authority.id,
                provider=AuthorizedDeltaRuleProvider(),
            )
        authority.delta_components = [{"component": "gross_wages", "amount": "0"}]
        await session.flush()
        with pytest.raises(AdjustmentCalculationError, match="integrity|zero"):
            await calculator.calculate(
                session,
                context=calculation_context(values),
                adjustment_id=authority.id,
                provider=AuthorizedDeltaRuleProvider(),
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_employee_period_and_currency_scope_are_reverified_at_calculation(
    finalization_database: tuple[async_sessionmaker[AsyncSession], dict[str, object]],
) -> None:
    factory, values = finalization_database
    async with factory() as session:
        tax, _ = await approved_tax_result(session, values)
        tax_employee_id = tax.employee_id
        tax_pay_period_id = tax.pay_period_id
        base = DraftPayrollAdjustment(
            classification=PayrollCorrectionType.TAX_CORRECTION,
            reason_code="synthetic_scope_test",
            source_type="tax_result",
            source_id=tax.id,
            source_digest=tax.calculation_digest,
            currency=tax.currency,
            effective_date=date(2026, 9, 20),
            evidence_digest=canonical_digest({"synthetic-scope": True}),
            delta_components=(
                EconomicDelta("employee_tax_withholding", Decimal("1.00")),
            ),
            employee_id=uuid4(),
            original_pay_period_id=tax.pay_period_id,
        )
        authority = await approved_adjustment(session, values, base)
        calculator = PayrollAdjustmentCalculationService(
            runtime_environment=RuleEnvironment.TEST
        )
        with pytest.raises(AdjustmentCalculationError, match="Employee"):
            await calculator.calculate(
                session,
                context=calculation_context(values),
                adjustment_id=authority.id,
                provider=SyntheticTaxAdjustmentProvider(),
            )

        authority.employee_id = tax_employee_id
        authority.original_pay_period_id = uuid4()
        await session.flush()
        with pytest.raises(AdjustmentCalculationError, match="pay-period"):
            await calculator.calculate(
                session,
                context=calculation_context(values),
                adjustment_id=authority.id,
                provider=SyntheticTaxAdjustmentProvider(),
            )
        await session.rollback()

        await session.refresh(authority)
        authority.employee_id = tax_employee_id
        authority.original_pay_period_id = tax_pay_period_id
        authority.currency = "EUR"
        await session.flush()
        with pytest.raises(AdjustmentCalculationError, match="currency"):
            await calculator.calculate(
                session,
                context=calculation_context(values),
                adjustment_id=authority.id,
                provider=SyntheticTaxAdjustmentProvider(),
            )
        await session.rollback()


def test_posted_and_unposted_accounting_consequences_are_non_mutating() -> None:
    posted: Any = SimpleNamespace(source_type="posted_accounting_journal")
    posted_consequences = PayrollAdjustmentCalculationService._consequences(
        posted, PayrollCorrectionType.RETROACTIVE_EARNINGS
    )
    assert posted_consequences == (
        AdjustmentConsequenceType.SUCCESSOR_PAYROLL_REQUIRED,
        AdjustmentConsequenceType.ACCOUNTING_ADJUSTMENT_REQUIRED,
    )
    assert PayrollAdjustmentCalculationService._recognition(
        posted, PayrollCorrectionType.RETROACTIVE_EARNINGS, "gross_wages"
    ) is RecognitionEffect.ACCOUNTING_ADJUSTMENT

    unposted: Any = SimpleNamespace(source_type="payroll_posting_fact_candidate")
    assert PayrollAdjustmentCalculationService._consequences(
        unposted, PayrollCorrectionType.ACCOUNTING_ADJUSTMENT_REQUIRED
    ) == (
        AdjustmentConsequenceType.ACCOUNTING_ADJUSTMENT_REQUIRED,
        AdjustmentConsequenceType.UNPOSTED_POSTING_FACT_SUPERSESSION,
    )
