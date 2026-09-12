from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.payroll.contracts import PayrollConflictError, canonical_digest
from app.payroll.real_employee_readiness_wiring import (
    REFERENCE_VERSION,
    AssemblyEvidence,
    AssemblyState,
    SetupValue,
    assemble_real_employee_readiness,
)
from app.payroll.real_input_readiness import EmployeePayrollStatus
from app.payroll.tax_authority import ProtectedPayrollInputCipher

EMPLOYEE = UUID("10000000-0000-0000-0000-000000000001")
COMPANY = UUID("20000000-0000-0000-0000-000000000001")
BRANCH = UUID("30000000-0000-0000-0000-000000000001")


VALUES = {
    "w4_filing_status": "single_or_married_filing_separately",
    "w4_step_2": False,
    "w4_step_3": Decimal(0),
    "w4_step_4a": Decimal(0),
    "w4_step_4b": Decimal(0),
    "w4_step_4c": Decimal(0),
    "work_jurisdiction": "US-FL",
    "residence_jurisdiction": "US-FL",
    "unemployment_workforce_jurisdiction": "US-FL",
    "deduction_configuration": "none-approved",
    "deduction_tax_treatment": "not_applicable",
    "deduction_effective_date": "2026-01-01",
    "deduction_limits": "not_applicable",
    "social_security_wages_ytd": Decimal(184000),
    "social_security_tax_ytd": Decimal(11408),
    "social_security_applicability": "applicable",
    "medicare_wages_ytd": Decimal(199750),
    "medicare_tax_ytd": Decimal("2896.38"),
    "medicare_applicability": "applicable",
    "additional_medicare_prerequisites": "complete",
    "federal_withholding_ytd": Decimal(25000),
    "prior_payroll_coverage": "reconciled-2026",
    "fixture_gross_wages": Decimal(1000),
}


def setup_value(
    key: str,
    value: object,
    *,
    employee: UUID = EMPLOYEE,
    year: int = 2026,
    start: date = date(2026, 1, 1),
) -> SetupValue:
    return SetupValue(
        key,
        employee,
        year,
        start,
        None,
        uuid4(),
        1,
        canonical_digest({"authority": key, "employee": str(employee), "year": year}),
        canonical_digest({"protected": key}),
        value,
    )


def evidence(
    *, omit: frozenset[str] = frozenset(), values: dict[str, object] | None = None
) -> AssemblyEvidence:
    source = values or VALUES
    return AssemblyEvidence(
        COMPANY,
        BRANCH,
        EMPLOYEE,
        True,
        date(2026, 6, 22),
        date(2026, 6, 28),
        "weekly",
        "hourly",
        uuid4(),
        date(2026, 1, 1),
        None,
        EMPLOYEE,
        "a" * 64,
        tuple(
            setup_value(key, value) for key, value in source.items() if key not in omit
        ),
        REFERENCE_VERSION,
    )


def test_complete_employee_is_ready_and_fixture_preview_is_non_transmitting() -> None:
    result = assemble_real_employee_readiness(evidence(), allow_fixture_preview=True)
    assert result.readiness.employees[0].status is EmployeePayrollStatus.PAYROLL_READY
    assert result.state is AssemblyState.CALCULATION_PREVIEW
    assert len(result.preview) == 6
    assert next(
        item for item in result.preview if item.component == "social_security_employee"
    ).amount == Decimal("31.00")
    assert next(
        item
        for item in result.preview
        if item.component == "additional_medicare_employee"
    ).amount == Decimal("6.75")


@pytest.mark.parametrize(
    ("omitted", "blocker"),
    [
        (frozenset({"w4_filing_status"}), "missing w4_filing_status"),
        (frozenset({"social_security_wages_ytd"}), "missing social_security_wages_ytd"),
    ],
)
def test_missing_setup_evidence_blocks(omitted: frozenset[str], blocker: str) -> None:
    result = assemble_real_employee_readiness(
        evidence(omit=omitted), allow_fixture_preview=True
    )
    assert result.state is AssemblyState.READINESS
    assert blocker in result.exact_blockers
    assert result.preview == ()


def test_missing_compensation_time_and_period_each_block() -> None:
    base = evidence()
    cases = (
        (replace(base, compensation_authority_id=None), "missing compensation_rate"),
        (replace(base, accepted_time_employee_id=None), "missing accepted_paid_time"),
        (
            replace(base, period_start=None, period_end=None),
            "missing payroll_period_assignment",
        ),
    )
    for item, blocker in cases:
        assert blocker in assemble_real_employee_readiness(item).exact_blockers


def test_missing_or_out_of_date_tax_rule_authority_blocks() -> None:
    result = assemble_real_employee_readiness(
        replace(evidence(), period_start=date(2027, 1, 1), period_end=date(2027, 1, 7))
    )
    assert "missing federal_tax_table" in result.exact_blockers


@pytest.mark.parametrize(
    "status",
    [
        "single_or_married_filing_separately",
        "married_filing_jointly",
        "head_of_household",
    ],
)
def test_filing_status_variants_resolve_without_defaults(status: str) -> None:
    values = {**VALUES, "w4_filing_status": status}
    result = assemble_real_employee_readiness(
        evidence(values=values), allow_fixture_preview=True
    )
    assert result.state is AssemblyState.CALCULATION_PREVIEW


def test_explicit_florida_evidence_is_not_applicable() -> None:
    fields = assemble_real_employee_readiness(evidence()).readiness.employees[0]
    assert "missing state_local_withholding_configuration" not in fields.exact_blockers
    assert "missing state_local_tax_table" not in fields.exact_blockers


def test_effective_transition_selects_one_version_and_overlap_conflicts() -> None:
    base = evidence()
    old = setup_value("w4_step_4c", Decimal(0), start=date(2026, 1, 1))
    newer = setup_value("w4_step_4c", Decimal(25), start=date(2026, 6, 1))
    without = tuple(item for item in base.setup_values if item.key != "w4_step_4c")
    result = assemble_real_employee_readiness(
        replace(base, setup_values=without + (old, newer))
    )
    assert "conflicting w4_step_4c" in result.exact_blockers

    valid = assemble_real_employee_readiness(
        replace(
            base,
            setup_values=without
            + (replace(old, effective_to=date(2026, 5, 31)), newer),
        ),
        allow_fixture_preview=True,
    )
    assert valid.state is AssemblyState.CALCULATION_PREVIEW


def test_foreign_employee_and_wrong_year_evidence_conflict() -> None:
    base = evidence(omit=frozenset({"w4_step_2", "social_security_wages_ytd"}))
    altered = base.setup_values + (
        setup_value("w4_step_2", False, employee=uuid4()),
        setup_value("social_security_wages_ytd", Decimal(0), year=2025),
    )
    result = assemble_real_employee_readiness(replace(base, setup_values=altered))
    assert "conflicting w4_step_2" in result.exact_blockers
    assert "conflicting social_security_wages_ytd" in result.exact_blockers


def test_encrypted_input_round_trip_rotation_and_tamper_protection() -> None:
    cipher = ProtectedPayrollInputCipher(
        active_key_id="v2", keys={"v1": b"1" * 32, "v2": b"2" * 32}
    )
    payload = {"value": "head_of_household"}
    kid, nonce, ciphertext, digest = cipher.encrypt(company_id=COMPANY, payload=payload)
    assert kid == "v2"
    assert (
        cipher.decrypt(
            company_id=COMPANY,
            key_id=kid,
            nonce=nonce,
            ciphertext=ciphertext,
            expected_digest=digest,
        )
        == payload
    )
    with pytest.raises(PayrollConflictError):
        cipher.decrypt(
            company_id=COMPANY,
            key_id=kid,
            nonce=nonce,
            ciphertext=ciphertext,
            expected_digest="0" * 64,
        )


def test_readiness_and_preview_never_project_sensitive_values() -> None:
    secret = "sensitive-election-canary"
    result = assemble_real_employee_readiness(
        evidence(values={**VALUES, "w4_step_4c": secret})
    )
    assert secret not in repr(result)
    assert all(secret not in blocker for blocker in result.exact_blockers)
