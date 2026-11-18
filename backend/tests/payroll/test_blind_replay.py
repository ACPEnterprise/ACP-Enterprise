import csv
import io
import json
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.payroll.blind_replay import (
    AuthorityClassification,
    BlindReplayError,
    BlindReplayInput,
    CompensationType,
    DeductionInput,
    DeductionTreatment,
    EmployeeReplayInput,
    EmploymentStatus,
    OpeningYTD,
    SourceProvenance,
    VarianceClassification,
    assert_shadow_role,
    calculate_shadow_payroll,
    collect_readiness,
    compare_frozen_to_qbo,
    import_qbo_answer_key_csv,
    import_qbo_answer_key_reports,
    owner_comparison_html,
    parse_blind_replay_input,
    readiness_missing_fields,
)
from app.payroll.federal_tax_rules_2026 import FilingStatus, PayFrequency

ENGINE_SHA = "a" * 40
WHEN = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)


def provenance(label: str) -> SourceProvenance:
    return SourceProvenance(
        label,
        date(2026, 1, 1),
        (label.encode().hex() * 64)[:64].ljust(64, "0"),
        AuthorityClassification.VERIFIED,
    )


def employee(**changes: object) -> EmployeeReplayInput:
    base = EmployeeReplayInput(
        employee_id=uuid4(),
        display_label="Synthetic Technician",
        employment_status=EmploymentStatus.ACTIVE,
        compensation_type=CompensationType.HOURLY,
        compensation_rate=Decimal(25),
        compensation_effective_start=date(2026, 1, 1),
        compensation_effective_end=None,
        regular_hours=Decimal(40),
        overtime_hours=Decimal(0),
        other_paid_hours=Decimal(0),
        overtime_multiplier=Decimal("1.5"),
        commission=Decimal(0),
        bonus=Decimal(0),
        other_authorized_earnings=Decimal(0),
        reimbursement=Decimal(0),
        filing_status=FilingStatus.SINGLE_OR_MARRIED_FILING_SEPARATELY,
        w4_step_2=False,
        w4_step_3=Decimal(0),
        w4_step_4a=Decimal(0),
        w4_step_4b=Decimal(0),
        w4_step_4c=Decimal(0),
        fica_applicable=True,
        work_state="US-FL",
        residence_state="US-FL",
        local_jurisdiction=None,
        state_income_tax=Decimal(0),
        local_income_tax=Decimal(0),
        deductions=(),
        opening_ytd=OpeningYTD(
            Decimal(10000),
            Decimal(10000),
            Decimal(10000),
            Decimal(10000),
            Decimal(500),
            Decimal(620),
            Decimal(145),
            Decimal(7000),
            Decimal(7000),
            {},
            provenance("opening-ytd"),
        ),
        futa_rate=Decimal("0.006"),
        futa_wage_base=Decimal(7000),
        suta_rate=Decimal("0.027"),
        suta_wage_base=Decimal(7000),
        compensation_provenance=provenance("compensation"),
        time_provenance=provenance("time"),
        tax_provenance=provenance("tax"),
        jurisdiction_provenance=provenance("jurisdiction"),
    )
    return replace(base, **changes)


def packet(value: EmployeeReplayInput) -> BlindReplayInput:
    return BlindReplayInput(
        uuid4(),
        date(2026, 11, 1),
        date(2026, 11, 14),
        date(2026, 11, 18),
        PayFrequency.BIWEEKLY,
        (value,),
        provenance("packet"),
    )


@pytest.mark.parametrize(
    ("case", "value", "expected_gross"),
    (
        ("A hourly technician", employee(), "1000.00"),
        ("B overtime technician", employee(overtime_hours=Decimal(8)), "1300.00"),
        ("C technician commission", employee(commission=Decimal(350)), "1350.00"),
        (
            "D overtime and commission",
            employee(overtime_hours=Decimal(8), commission=Decimal(350)),
            "1650.00",
        ),
        (
            "E helper",
            employee(display_label="Synthetic Helper", compensation_rate=Decimal(18)),
            "720.00",
        ),
        (
            "F manager salary",
            employee(
                display_label="Synthetic Manager",
                compensation_type=CompensationType.SALARY,
                compensation_rate=Decimal(78000),
                regular_hours=Decimal(0),
            ),
            "3000.00",
        ),
        ("G bonus", employee(bonus=Decimal(500)), "1500.00"),
        ("H reimbursement", employee(reimbursement=Decimal("125.50")), "1000.00"),
        (
            "I pre-tax deduction",
            employee(
                deductions=(
                    DeductionInput(
                        "HEALTH",
                        Decimal(100),
                        DeductionTreatment.PRE_TAX_FEDERAL_AND_FICA,
                        Decimal(50),
                        provenance("health"),
                    ),
                )
            ),
            "1000.00",
        ),
        (
            "J post-tax deduction",
            employee(
                deductions=(
                    DeductionInput(
                        "GARNISHMENT",
                        Decimal(75),
                        DeductionTreatment.POST_TAX,
                        Decimal(0),
                        provenance("garnishment"),
                    ),
                )
            ),
            "1000.00",
        ),
        (
            "K Social Security wage base edge",
            employee(
                opening_ytd=replace(
                    employee().opening_ytd,
                    social_security_wages=Decimal(184000),
                )
            ),
            "1000.00",
        ),
        (
            "L Additional Medicare edge",
            employee(
                opening_ytd=replace(
                    employee().opening_ytd,
                    medicare_wages=Decimal(199800),
                )
            ),
            "1000.00",
        ),
        (
            "N rounding edge",
            employee(
                compensation_rate=Decimal("18.3333"), regular_hours=Decimal("7.3333")
            ),
            "134.44",
        ),
        (
            "O commission only",
            employee(regular_hours=Decimal(0), commission=Decimal(800)),
            "800.00",
        ),
        (
            "P terminated final calculation",
            employee(employment_status=EmploymentStatus.TERMINATED_FINAL_PAY),
            "1000.00",
        ),
    ),
)
def test_acp_relevant_matrix(
    case: str, value: EmployeeReplayInput, expected_gross: str
) -> None:
    result = calculate_shadow_payroll(
        packet(value), engine_sha=ENGINE_SHA, calculated_at=WHEN
    )
    item = result.employees[0]
    assert item.gross_pay == Decimal(expected_gross), case
    assert item.journal.accounting_delta == Decimal("0.00"), case
    assert item.net_pay >= 0
    assert item.total_employer_cost >= item.gross_pay + item.reimbursement
    assert result.frozen_before_qbo_reveal is True


def test_pretax_posttax_reimbursement_and_wage_base_behavior() -> None:
    pretax = calculate_shadow_payroll(
        packet(
            employee(
                deductions=(
                    DeductionInput(
                        "401K",
                        Decimal(100),
                        DeductionTreatment.PRE_TAX_FEDERAL_AND_FICA,
                        Decimal(25),
                        provenance("401k"),
                    ),
                )
            )
        ),
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN,
    ).employees[0]
    posttax = calculate_shadow_payroll(
        packet(
            employee(
                deductions=(
                    DeductionInput(
                        "POST",
                        Decimal(100),
                        DeductionTreatment.POST_TAX,
                        Decimal(0),
                        provenance("post"),
                    ),
                )
            )
        ),
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN,
    ).employees[0]
    reimbursed = calculate_shadow_payroll(
        packet(employee(reimbursement=Decimal(125))),
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN,
    ).employees[0]
    assert pretax.fit_taxable_wages == Decimal(900)
    assert pretax.social_security_taxable_wages == Decimal(900)
    assert posttax.fit_taxable_wages == Decimal(1000)
    assert reimbursed.gross_pay == Decimal(1000)
    assert reimbursed.net_pay - calculate_shadow_payroll(
        packet(employee()), engine_sha=ENGINE_SHA, calculated_at=WHEN
    ).employees[0].net_pay == Decimal(125)


def test_ytd_accumulation_edges_and_freeze_versioning() -> None:
    first_packet = packet(
        employee(
            opening_ytd=replace(
                employee().opening_ytd,
                social_security_wages=Decimal(184000),
                medicare_wages=Decimal(199800),
            )
        )
    )
    first = calculate_shadow_payroll(
        first_packet, engine_sha=ENGINE_SHA, calculated_at=WHEN
    )
    second = calculate_shadow_payroll(
        first_packet,
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN.replace(minute=1),
    )
    assert first.employees[0].social_security_taxable_wages == Decimal(500)
    assert first.employees[0].additional_medicare == Decimal("7.20")
    assert first.calculation_id != second.calculation_id
    assert first.input_digest == second.input_digest
    assert first.result_digest != second.result_digest


def _answer_csv(result) -> bytes:  # type: ignore[no-untyped-def]
    item = result.employees[0]
    headers = (
        "employee,pay date,regular pay,overtime pay,commission,bonus,gross pay,"
        "fit taxable wages,social security wages,medicare wages,federal withholding,"
        "employee social security,employee medicare,other taxes,pre-tax deductions,"
        "post-tax deductions,net pay,employer social security,employer medicare,"
        "unemployment,employer contributions,total employer cost\n"
    )
    values = (
        f"{item.display_label},2026-11-18,{item.regular_pay},{item.overtime_pay},"
        f"{item.commission},{item.bonus},{item.gross_pay},{item.fit_taxable_wages},"
        f"{item.social_security_taxable_wages},{item.medicare_taxable_wages},"
        f"{item.federal_withholding},{item.employee_social_security},{item.employee_medicare},"
        f"{item.state_local_taxes + item.additional_medicare},{item.pretax_deductions},"
        f"{item.posttax_deductions},{item.net_pay},{item.employer_social_security},"
        f"{item.employer_medicare},{item.futa + item.suta},{item.employer_contributions},"
        f"{item.total_employer_cost}\n"
    )
    return (headers + values).encode()


def test_answer_key_isolation_deduplication_variance_and_owner_report() -> None:
    company_id = uuid4()
    value = employee()
    source = replace(packet(value), company_id=company_id)
    frozen = calculate_shadow_payroll(source, engine_sha=ENGINE_SHA, calculated_at=WHEN)
    with pytest.raises(BlindReplayError, match="before shadow freeze"):
        import_qbo_answer_key_csv(
            b"anything",
            company_id=company_id,
            report_type="Payroll Details",
            frozen_result=None,
        )
    answer = import_qbo_answer_key_csv(
        _answer_csv(frozen),
        company_id=company_id,
        report_type="Payroll Details",
        frozen_result=frozen,
    )
    replay = import_qbo_answer_key_csv(
        _answer_csv(frozen),
        company_id=company_id,
        report_type="Payroll Details",
        frozen_result=frozen,
    )
    assert answer.source_file_digest == replay.source_file_digest
    assert answer.answer_key_digest == replay.answer_key_digest
    comparison = compare_frozen_to_qbo(frozen, answer)
    assert comparison.unexplained_count == 0
    assert all(
        line.classification is VarianceClassification.EXACT_MATCH
        for line in comparison.lines
    )
    rendered = owner_comparison_html(comparison)
    assert "TwelveHats Shadow Payroll vs QuickBooks" in rendered
    assert value.display_label in rendered
    duplicated = _answer_csv(frozen) + _answer_csv(frozen).split(b"\n", 1)[1]
    with pytest.raises(BlindReplayError, match="duplicate Employee/paycheck"):
        import_qbo_answer_key_csv(
            duplicated,
            company_id=company_id,
            report_type="Payroll Details",
            frozen_result=frozen,
        )


def test_contract_rejects_missing_or_conflicting_inputs_and_security_is_least_privilege() -> (
    None
):
    with pytest.raises(BlindReplayError, match="provenance"):
        packet(
            employee(tax_provenance=replace(provenance("bad"), evidence_digest=""))
        ).validate()
    with pytest.raises(BlindReplayError, match="effective"):
        packet(employee(compensation_effective_start=date(2026, 11, 2))).validate()
    with pytest.raises(PermissionError):
        assert_shadow_role(("COMPANY_TECHNICIAN_FIELD_READ",))
    assert_shadow_role(("COMPANY_PAYROLL_CALCULATION_EXECUTE",))
    missing = readiness_missing_fields(None)
    assert "w4_step_4c" in missing["PAYROLL_INPUT_PACKET"]
    assert "opening_ytd.social_security_wages" in missing["PAYROLL_INPUT_PACKET"]
    assert readiness_missing_fields(packet(employee()))["Synthetic Technician"] == ()
    collected = collect_readiness(
        ({"employee": "Dakota Wilcox", "compensation_rate": "present"},)
    )["Dakota Wilcox"]
    assert collected["compensation_rate"] == "PRESENT"
    assert collected["w4_step_4c"] == "MISSING"


def test_multiple_qbo_reports_merge_only_after_freeze() -> None:
    company_id = uuid4()
    frozen = calculate_shadow_payroll(
        replace(packet(employee()), company_id=company_id),
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN,
    )
    complete = _answer_csv(frozen).decode().splitlines()
    headings = complete[0].split(",")
    values = complete[1].split(",")
    midpoint = 12
    first_fields = [0, 1, *range(2, midpoint)]
    second_fields = [0, 1, *range(midpoint, len(headings))]

    def subset(fields: list[int]) -> bytes:
        return (
            ",".join(headings[index] for index in fields)
            + "\n"
            + ",".join(values[index] for index in fields)
            + "\n"
        ).encode()

    answer = import_qbo_answer_key_reports(
        (
            ("Payroll Details", subset(first_fields)),
            ("Total Payroll Cost", subset(second_fields)),
        ),
        company_id=company_id,
        frozen_result=frozen,
    )
    assert len(answer.employees) == 1
    assert compare_frozen_to_qbo(frozen, answer).unexplained_count == 0


def test_material_variance_requires_reviewed_classification_and_digests_are_enforced() -> (
    None
):
    company_id = uuid4()
    frozen = calculate_shadow_payroll(
        replace(packet(employee()), company_id=company_id),
        engine_sha=ENGINE_SHA,
        calculated_at=WHEN,
    )
    rows = list(csv.DictReader(io.StringIO(_answer_csv(frozen).decode())))
    rows[0]["gross pay"] = "1001.00"
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=tuple(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    payload = output.getvalue().encode()
    answer = import_qbo_answer_key_csv(
        payload,
        company_id=company_id,
        report_type="Payroll Details",
        frozen_result=frozen,
    )
    unresolved = compare_frozen_to_qbo(frozen, answer)
    assert any(
        line.component == "gross_pay"
        and line.classification is VarianceClassification.UNRESOLVED
        for line in unresolved.lines
    )
    reviewed = compare_frozen_to_qbo(
        frozen,
        answer,
        reviewed_classifications={
            ("Synthetic Technician", "gross_pay"): (
                VarianceClassification.INPUT_DIFFERENCE,
                "QuickBooks export used a different commission input.",
            )
        },
    )
    assert any(
        line.component == "gross_pay"
        and line.classification is VarianceClassification.INPUT_DIFFERENCE
        for line in reviewed.lines
    )
    with pytest.raises(BlindReplayError, match="digest is invalid"):
        import_qbo_answer_key_csv(
            payload,
            company_id=company_id,
            report_type="Payroll Details",
            frozen_result=replace(frozen, result_digest="0" * 64),
        )


def test_real_packet_parser_rejects_missing_and_selected_period_outputs() -> None:
    source = packet(employee())
    payload = json.loads(json.dumps(asdict(source), default=str))
    parsed = parse_blind_replay_input(payload)
    assert parsed == source
    del payload["employees"][0]["w4_step_4c"]
    with pytest.raises(BlindReplayError, match="missing w4_step_4c"):
        parse_blind_replay_input(payload)
    payload = json.loads(json.dumps(asdict(source), default=str))
    payload["employees"][0]["net_pay"] = "answer-key-value"
    with pytest.raises(BlindReplayError, match="forbidden before freeze"):
        parse_blind_replay_input(payload)
