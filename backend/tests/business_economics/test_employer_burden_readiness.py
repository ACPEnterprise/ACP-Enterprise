from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.business_economics.employer_burden_readiness import project_employer_burden


def component(key: str, amount: str) -> dict[str, object]:
    return {
        "component_key": key,
        "kind": "tax",
        "responsibility": "employer_payroll_tax",
        "amount": amount,
        "authority_digest": "a" * 64,
        "evidence_digest": "b" * 64,
        "provider_id": "authority-provider",
        "provider_version": "2026.1",
        "jurisdiction_reference": "US",
    }


def test_approved_employer_components_are_projected_without_job_allocation() -> None:
    tax = SimpleNamespace(
        employee_id=uuid4(),
        pay_period_id=uuid4(),
        currency="USD",
        employer_contribution_total=Decimal("76.50"),
        components=(
            component("employer_social_security", "62.00"),
            component("employer_medicare", "14.50"),
        ),
        calculation_digest="c" * 64,
    )
    gross = SimpleNamespace(period_start=date(2026, 9, 1), period_end=date(2026, 9, 7))

    result = project_employer_burden(
        rows=((tax, gross),),
        company_id=str(uuid4()),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["source_state"] == "AUTHORITATIVE_READY"
    assert result["authoritative_employer_burden_total"] == "76.50"
    assert result["readiness"]["employer_social_security"] == "AUTHORITATIVE_READY"
    assert result["readiness"]["workers_compensation"] == "ACCOUNTANT_INPUT_REQUIRED"
    assert (
        result["employee_periods"][0]["job_attribution_state"]
        == "OWNER_POLICY_REQUIRED"
    )
    assert result["mutation_authority"] == "none"


def test_component_total_conflict_fails_closed() -> None:
    tax = SimpleNamespace(
        employee_id=uuid4(),
        pay_period_id=uuid4(),
        currency="USD",
        employer_contribution_total=Decimal("80.00"),
        components=(component("employer_social_security", "62.00"),),
        calculation_digest="c" * 64,
    )
    gross = SimpleNamespace(period_start=date(2026, 9, 1), period_end=date(2026, 9, 7))
    result = project_employer_burden(
        rows=((tax, gross),),
        company_id=str(uuid4()),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["source_state"] == "CONFLICTING"
    assert result["authoritative_employer_burden_total"] is None


def test_missing_payroll_population_is_missing_not_zero() -> None:
    result = project_employer_burden(
        rows=(),
        company_id=str(uuid4()),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert result["source_state"] == "SOURCE_MISSING"
    assert result["authoritative_employer_burden_total"] is None
