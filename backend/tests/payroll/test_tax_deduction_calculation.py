from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.payroll.contracts import PayrollAuthorizationError, canonical_digest
from app.payroll.permissions import PayrollPermission
from app.payroll.tax_authority import (
    AuthorityRequirement,
    AuthorityResolution,
    PayrollInputDomain,
    TaxDeductionAdmissionResult,
    TaxDeductionAdmissionState,
)
from app.payroll.tax_calculation import (
    ApprovedGrossPayEvidence,
    ComponentKind,
    DeductionBasis,
    DeductionInstruction,
    EmployerContributionInstruction,
    PayrollTaxDeductionCalculationEngine,
    ProviderEnvironment,
    SyntheticRateTaxProvider,
    TaxComponentInstruction,
    TaxDeductionCalculationError,
    TaxResponsibility,
)
from tests.payroll.test_gross_pay_calculation import (
    NOW,
    calculate,
    compensation,
    policy,
    time_input,
)


def gross_evidence(minutes: int = 40 * 60) -> ApprovedGrossPayEvidence:
    company_id, employee_id = uuid4(), uuid4()
    result = calculate(
        policy(company_id),
        compensation(company_id, employee_id, rate=Decimal("25.00")),
        time_input(company_id, employee_id, minutes),
    )
    return ApprovedGrossPayEvidence(
        persisted_result_id=uuid4(),
        persisted_lifecycle="approved",
        persisted_company_id=company_id,
        persisted_employee_id=employee_id,
        persisted_pay_period_id=result.pay_period.pay_period_id,
        persisted_calculation_digest=result.calculation_digest,
        persisted_currency=result.currency,
        persisted_gross_pay_total=result.gross_pay_total,
        candidate=result,
    )


def resolution(
    gross: ApprovedGrossPayEvidence,
    domain: PayrollInputDomain,
    key: str,
    *,
    protected: bool = False,
    state: TaxDeductionAdmissionState = TaxDeductionAdmissionState.READY,
) -> AuthorityResolution:
    return AuthorityResolution(
        requirement=AuthorityRequirement(
            domain=domain,
            authority_key=key,
            employee_id=gross.persisted_employee_id,
        ),
        state=state,
        authority_id=uuid4() if state is TaxDeductionAdmissionState.READY else None,
        authority_digest=(
            canonical_digest({"synthetic-authority": key})
            if state is TaxDeductionAdmissionState.READY
            else None
        ),
        protected_input_digest=(
            canonical_digest({"synthetic-protected-input": key})
            if protected
            else None
        ),
        limitations=(),
    )


def admission(
    gross: ApprovedGrossPayEvidence,
    resolutions: tuple[AuthorityResolution, ...],
    *,
    state: TaxDeductionAdmissionState = TaxDeductionAdmissionState.READY,
    company_id: UUID | None = None,
) -> TaxDeductionAdmissionResult:
    provisional = TaxDeductionAdmissionResult(
        company_id=company_id or gross.persisted_company_id,
        employee_id=gross.persisted_employee_id,
        gross_result_id=gross.persisted_result_id,
        gross_calculation_digest=gross.persisted_calculation_digest,
        as_of_date=date(2026, 9, 4),
        definition_version="payroll.tax-deduction-admission.v1",
        state=state,
        resolutions=resolutions,
        blockers=(f"synthetic:{state.value}",) if state not in {
            TaxDeductionAdmissionState.READY,
            TaxDeductionAdmissionState.NOT_APPLICABLE,
        } else (),
        admission_digest="",
    )
    return replace(
        provisional,
        admission_digest=canonical_digest(provisional.canonical_content()),
    )


def tax_instruction(
    value: AuthorityResolution,
    *,
    key: str,
    responsibility: TaxResponsibility,
    rate: str,
    provider_version: str = "synthetic-tax-v1",
    protected: bool = False,
) -> TaxComponentInstruction:
    assert value.authority_id is not None and value.authority_digest is not None
    return TaxComponentInstruction(
        component_key=key,
        responsibility=responsibility,
        authority_id=value.authority_id,
        authority_digest=value.authority_digest,
        jurisdiction_reference="synthetic-jurisdiction",
        requires_protected_input=protected,
        provider=SyntheticRateTaxProvider(
            provider_id="synthetic-test-provider",
            provider_version=provider_version,
            rate=Decimal(rate),
        ),
    )


def deduction_instruction(
    value: AuthorityResolution,
    *,
    key: str,
    priority: int,
    basis: DeductionBasis,
    fixed: str | None = None,
    percentage: str | None = None,
    cap: str | None = None,
) -> DeductionInstruction:
    assert value.authority_id is not None and value.authority_digest is not None
    return DeductionInstruction(
        component_key=key,
        authority_id=value.authority_id,
        authority_digest=value.authority_digest,
        basis=basis,
        priority=priority,
        currency="USD",
        fixed_amount=Decimal(fixed) if fixed is not None else None,
        percentage=Decimal(percentage) if percentage is not None else None,
        cap_amount=Decimal(cap) if cap is not None else None,
    )


def engine() -> PayrollTaxDeductionCalculationEngine:
    return PayrollTaxDeductionCalculationEngine(
        runtime_environment=ProviderEnvironment.TEST
    )


def execute(**values):  # type: ignore[no-untyped-def]
    values.setdefault("calculated_at", NOW)
    return engine().calculate(
        actor_permissions=frozenset(
            {PayrollPermission.TAX_CALCULATION_EXECUTE}
        ),
        **values,
    )


def test_no_applicable_authority_produces_zero_components_and_full_net() -> None:
    gross = gross_evidence()
    result = execute(
        gross=gross,
        admission=admission(
            gross, (), state=TaxDeductionAdmissionState.NOT_APPLICABLE
        ),
    )
    result.verify()
    assert result.components == ()
    assert result.net_pay_candidate == result.gross_pay
    assert result.total_employee_taxes == Decimal("0.00")


def test_employee_withholding_and_payroll_counterparts_are_distinct() -> None:
    gross = gross_evidence()
    withholding = resolution(
        gross, PayrollInputDomain.TAX, "synthetic_withholding", protected=True
    )
    employee_tax = resolution(gross, PayrollInputDomain.TAX, "synthetic_employee_tax")
    employer_tax = resolution(gross, PayrollInputDomain.TAX, "synthetic_employer_tax")
    result = execute(
        gross=gross,
        admission=admission(gross, (withholding, employee_tax, employer_tax)),
        tax_instructions=(
            tax_instruction(
                withholding,
                key="synthetic_withholding",
                responsibility=TaxResponsibility.EMPLOYEE_WITHHOLDING,
                rate="0.10",
                protected=True,
            ),
            tax_instruction(
                employee_tax,
                key="synthetic_employee_tax",
                responsibility=TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
                rate="0.05",
            ),
            tax_instruction(
                employer_tax,
                key="synthetic_employer_tax",
                responsibility=TaxResponsibility.EMPLOYER_PAYROLL_TAX,
                rate="0.05",
            ),
        ),
    )
    assert result.gross_pay == Decimal("1000.00")
    assert result.total_employee_taxes == Decimal("150.00")
    assert result.total_employer_contributions == Decimal("50.00")
    assert result.net_pay_candidate == Decimal("850.00")
    assert sum(
        item.amount
        for item in result.components
        if item.responsibility == TaxResponsibility.EMPLOYER_PAYROLL_TAX.value
    ) == Decimal("50.00")


def test_fixed_percentage_priority_cap_and_employer_contribution() -> None:
    gross = gross_evidence()
    fixed = resolution(gross, PayrollInputDomain.DEDUCTION, "fixed")
    percentage = resolution(gross, PayrollInputDomain.DEDUCTION, "percentage")
    employer = resolution(
        gross, PayrollInputDomain.EMPLOYER_CONTRIBUTION, "employer_benefit"
    )
    employer_instruction = EmployerContributionInstruction(
        component_key="employer_benefit",
        authority_id=employer.authority_id,  # type: ignore[arg-type]
        authority_digest=employer.authority_digest,  # type: ignore[arg-type]
        basis=DeductionBasis.PERCENTAGE_OF_GROSS,
        priority=1,
        currency="USD",
        percentage=Decimal("0.03"),
    )
    result = execute(
        gross=gross,
        admission=admission(gross, (fixed, percentage, employer)),
        deduction_instructions=(
            deduction_instruction(
                percentage,
                key="percentage",
                priority=20,
                basis=DeductionBasis.PERCENTAGE_OF_GROSS,
                percentage="0.10",
                cap="75.00",
            ),
            deduction_instruction(
                fixed,
                key="fixed",
                priority=10,
                basis=DeductionBasis.FIXED_AMOUNT,
                fixed="25.00",
            ),
        ),
        employer_contribution_instructions=(employer_instruction,),
    )
    deductions = tuple(
        item
        for item in result.components
        if item.kind is ComponentKind.EMPLOYEE_DEDUCTION
    )
    assert tuple(item.component_key for item in deductions) == ("fixed", "percentage")
    assert tuple(item.amount for item in deductions) == (
        Decimal("25.00"),
        Decimal("75.00"),
    )
    assert result.total_employee_deductions == Decimal("100.00")
    assert result.total_employer_contributions == Decimal("30.00")
    assert result.net_pay_candidate == Decimal("900.00")


@pytest.mark.parametrize(
    "blocked_state",
    [
        TaxDeductionAdmissionState.MISSING,
        TaxDeductionAdmissionState.EXPIRED,
        TaxDeductionAdmissionState.UNAPPROVED,
        TaxDeductionAdmissionState.CONFLICTING,
    ],
)
def test_blocked_admission_never_calculates(
    blocked_state: TaxDeductionAdmissionState,
) -> None:
    gross = gross_evidence()
    blocked = resolution(
        gross,
        PayrollInputDomain.TAX,
        "blocked",
        state=blocked_state,
    )
    with pytest.raises(TaxDeductionCalculationError, match="not ready"):
        execute(
            gross=gross,
            admission=admission(gross, (blocked,), state=blocked_state),
        )


def test_missing_protected_input_cross_scope_currency_and_permission_fail() -> None:
    gross = gross_evidence()
    tax = resolution(gross, PayrollInputDomain.TAX, "protected-required")
    instruction = tax_instruction(
        tax,
        key="protected-required",
        responsibility=TaxResponsibility.EMPLOYEE_WITHHOLDING,
        rate="0.10",
        protected=True,
    )
    with pytest.raises(TaxDeductionCalculationError, match="protected"):
        execute(
            gross=gross,
            admission=admission(gross, (tax,)),
            tax_instructions=(instruction,),
        )
    with pytest.raises(TaxDeductionCalculationError, match="scope"):
        execute(
            gross=gross,
            admission=admission(gross, (), company_id=uuid4()),
        )
    deduction = resolution(gross, PayrollInputDomain.DEDUCTION, "currency")
    wrong_currency = replace(
        deduction_instruction(
            deduction,
            key="currency",
            priority=1,
            basis=DeductionBasis.FIXED_AMOUNT,
            fixed="1.00",
        ),
        currency="CAD",
    )
    with pytest.raises(TaxDeductionCalculationError, match="currency"):
        execute(
            gross=gross,
            admission=admission(gross, (deduction,)),
            deduction_instructions=(wrong_currency,),
        )
    with pytest.raises(PayrollAuthorizationError):
        engine().calculate(
            actor_permissions=frozenset(),
            gross=gross,
            admission=admission(gross, ()),
            calculated_at=NOW,
        )


def test_replay_provider_and_gross_changes_and_production_synthetic_barrier() -> None:
    gross = gross_evidence()
    tax = resolution(gross, PayrollInputDomain.TAX, "versioned")
    first_instruction = tax_instruction(
        tax,
        key="versioned",
        responsibility=TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
        rate="0.02",
    )
    values = {
        "gross": gross,
        "admission": admission(gross, (tax,)),
        "tax_instructions": (first_instruction,),
    }
    first = execute(**values)
    replay = execute(**values, calculated_at=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert first.result_id == replay.result_id
    assert first.calculation_digest == replay.calculation_digest
    changed_provider = execute(
        gross=gross,
        admission=values["admission"],  # type: ignore[arg-type]
        tax_instructions=(
            tax_instruction(
                tax,
                key="versioned",
                responsibility=TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
                rate="0.02",
                provider_version="synthetic-tax-v2",
            ),
        ),
    )
    assert changed_provider.calculation_digest != first.calculation_digest
    changed_gross = gross_evidence(minutes=39 * 60)
    changed_tax = resolution(changed_gross, PayrollInputDomain.TAX, "versioned")
    changed = execute(
        gross=changed_gross,
        admission=admission(changed_gross, (changed_tax,)),
        tax_instructions=(
            tax_instruction(
                changed_tax,
                key="versioned",
                responsibility=TaxResponsibility.EMPLOYEE_PAYROLL_TAX,
                rate="0.02",
            ),
        ),
    )
    assert changed.gross_calculation_digest != first.gross_calculation_digest
    assert changed.calculation_digest != first.calculation_digest
    with pytest.raises(TaxDeductionCalculationError, match="synthetic"):
        PayrollTaxDeductionCalculationEngine(
            runtime_environment=ProviderEnvironment.PRODUCTION
        ).calculate(
            actor_permissions=frozenset(
                {PayrollPermission.TAX_CALCULATION_EXECUTE}
            ),
            gross=gross,
            admission=values["admission"],  # type: ignore[arg-type]
            tax_instructions=(first_instruction,),
            calculated_at=NOW,
        )


def test_negative_net_and_sensitive_safe_output_fail_closed() -> None:
    gross = gross_evidence()
    deduction = resolution(gross, PayrollInputDomain.DEDUCTION, "oversized")
    with pytest.raises(TaxDeductionCalculationError, match="negative net"):
        execute(
            gross=gross,
            admission=admission(gross, (deduction,)),
            deduction_instructions=(
                deduction_instruction(
                    deduction,
                    key="oversized",
                    priority=1,
                    basis=DeductionBasis.FIXED_AMOUNT,
                    fixed="1001.00",
                ),
            ),
        )
    tax = resolution(
        gross, PayrollInputDomain.TAX, "safe-output", protected=True
    )
    result = execute(
        gross=gross,
        admission=admission(gross, (tax,)),
        tax_instructions=(
            tax_instruction(
                tax,
                key="safe-output",
                responsibility=TaxResponsibility.EMPLOYEE_WITHHOLDING,
                rate="0.01",
                protected=True,
            ),
        ),
    )
    safe = repr(result.safe_event_evidence()).lower()
    assert "net_pay" not in safe
    assert "amount" not in safe
    assert "protected_input" not in safe
    assert "filing" not in safe
