from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.operational_measurement.foundation import (
    AttributionReadiness,
    Dimension,
    EvidenceState,
    FactClass,
    MeasurementFact,
    MeasurementPacket,
    TimeMeasure,
    ratio_input_readiness,
    source_matrix,
)

NOW = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)


def fact(company_id, branch_id, measure, value, *, employee_id=None, job_id=None):
    return MeasurementFact(
        fact_id=uuid4(),
        dimension=Dimension(
            company_id=company_id,
            branch_id=branch_id,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            employee_id=employee_id,
            job_id=job_id,
            service_category="plumbing",
        ),
        measure=measure,
        fact_class=FactClass.MEASURED_FACT,
        state=EvidenceState.AVAILABLE,
        value=Decimal(value),
        unit="minutes",
        source_authority="timekeeping",
        source_record_ids=(str(uuid4()),),
        source_version="timekeeping.workday-time.v1",
        observed_at=NOW,
        freshness_at=NOW,
        sample_count=1,
    )


def test_rich_synthetic_month_keeps_components_separate_and_deterministic():
    company, branch = uuid4(), uuid4()
    employees = (uuid4(), uuid4(), uuid4())
    shared_job, callback_job = uuid4(), uuid4()
    facts = (
        fact(company, branch, TimeMeasure.PAID_TIME, "28800", employee_id=employees[0]),
        fact(
            company,
            branch,
            TimeMeasure.AVAILABLE_TIME,
            "25200",
            employee_id=employees[0],
        ),
        fact(
            company,
            branch,
            TimeMeasure.SCHEDULED_TIME,
            "21000",
            employee_id=employees[0],
        ),
        fact(
            company,
            branch,
            TimeMeasure.ACTIVE_JOB_TIME,
            "17400",
            employee_id=employees[0],
        ),
        fact(company, branch, TimeMeasure.BREAK_TIME, "2400", employee_id=employees[0]),
        fact(
            company,
            branch,
            TimeMeasure.UNCLASSIFIED_TIME,
            "3000",
            employee_id=employees[0],
        ),
        fact(
            company,
            branch,
            TimeMeasure.ACTIVE_JOB_TIME,
            "240",
            employee_id=employees[1],
            job_id=shared_job,
        ),
        fact(
            company,
            branch,
            TimeMeasure.ACTIVE_JOB_TIME,
            "180",
            employee_id=employees[2],
            job_id=shared_job,
        ),
        fact(company, branch, "CALLBACK_COUNT", "1", job_id=callback_job),
        fact(company, branch, "ACTUAL_MATERIAL_CONSUMPTION", "3", job_id=shared_job),
        fact(company, branch, "ESTIMATE_PRESENTED_COUNT", "20"),
        fact(company, branch, "ESTIMATE_ACCEPTED_COUNT", "12"),
        fact(company, branch, "INVOICE_AMOUNT_MINOR", "980000"),
        fact(company, branch, "PAYMENT_AMOUNT_MINOR", "840000"),
        fact(company, branch, "FLEET_DOWNTIME_MINUTES", "960"),
    )
    packet = MeasurementPacket(
        packet_id=uuid4(),
        company_id=company,
        branch_id=branch,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        facts=facts,
        attribution=(
            AttributionReadiness(
                shared_job,
                employees[1:],
                EvidenceState.PARTIAL,
                "employee_time_evidence",
                "SOURCE_REQUIRED",
                "PARTIAL",
                ("employee_value_attribution", "complete_job_labor_cost"),
            ),
        ),
        source_matrix=source_matrix(),
        created_at=NOW,
    )
    replay = MeasurementPacket(
        packet_id=uuid4(),
        company_id=company,
        branch_id=branch,
        period_start=packet.period_start,
        period_end=packet.period_end,
        facts=facts,
        attribution=packet.attribution,
        source_matrix=packet.source_matrix,
        created_at=NOW,
    )
    assert packet.digest == replay.digest
    assert packet.readiness()["fact_count"] == 15
    ratios = {row["candidate"]: row for row in ratio_input_readiness(facts)}
    assert ratios["active_job_time_over_paid_time"]["state"] == "INPUTS_AVAILABLE"
    assert all(not row["selected_as_company_kpi"] for row in ratios.values())
    assert {f.measure for f in facts} >= {
        "INVOICE_AMOUNT_MINOR",
        "PAYMENT_AMOUNT_MINOR",
    }


def test_source_matrix_declares_exact_external_and_source_gates():
    matrix = {row["input"]: row["state"] for row in source_matrix()}
    assert matrix["travel_route_duration"] == "EXTERNAL_GATE"
    assert matrix["external_market_price_share"] == "EXTERNAL_GATE"
    assert matrix["callback_rework_identity"] == "SOURCE_REQUIRED"
    assert matrix["fleet_fuel_insurance_depreciation"] == "SOURCE_REQUIRED"
    assert matrix["job_pause_resume_history"] == "PARTIAL"


def test_adversarial_foreign_authority_and_false_precision_fail_closed():
    company, branch = uuid4(), uuid4()
    foreign = fact(uuid4(), branch, TimeMeasure.PAID_TIME, "60")
    with pytest.raises(ValueError, match="foreign Company"):
        MeasurementPacket(
            uuid4(),
            company,
            branch,
            date(2026, 8, 1),
            date(2026, 8, 31),
            (foreign,),
            (),
            source_matrix(),
            NOW,
        )
    with pytest.raises(ValueError, match="incomplete evidence"):
        MeasurementFact(
            uuid4(),
            Dimension(company, branch, date(2026, 8, 1), date(2026, 8, 31)),
            "TRAVEL_TIME",
            FactClass.MEASURED_FACT,
            EvidenceState.EXTERNAL_GATE,
            Decimal(30),
            "minutes",
            "routing",
            (),
            "none",
            NOW,
            None,
        )


def test_adversarial_policy_output_and_primary_multi_tech_attribution_rejected():
    company, branch = uuid4(), uuid4()
    with pytest.raises(ValueError, match="facts and derivations"):
        MeasurementFact(
            uuid4(),
            Dimension(company, branch, date(2026, 8, 1), date(2026, 8, 31)),
            "STAFFING_ACTION",
            FactClass.RECOMMENDATION,
            EvidenceState.AVAILABLE,
            "terminate",
            None,
            "model",
            (),
            "v1",
            NOW,
            NOW,
        )
    with pytest.raises(ValueError, match="cannot default to primary"):
        AttributionReadiness(
            uuid4(),
            (uuid4(), uuid4()),
            EvidenceState.PARTIAL,
            "primary_employee",
            "SOURCE_REQUIRED",
            "SOURCE_REQUIRED",
            (),
        )


def test_corrections_require_successor_reason_and_preserve_original_digest():
    company, branch = uuid4(), uuid4()
    original = fact(company, branch, TimeMeasure.PAID_TIME, "60")
    original_digest = original.digest
    with pytest.raises(ValueError, match="requires a reason"):
        MeasurementFact(
            uuid4(),
            original.dimension,
            original.measure,
            FactClass.MEASURED_FACT,
            EvidenceState.AVAILABLE,
            Decimal(90),
            "minutes",
            "timekeeping",
            ("corrected",),
            "v2",
            NOW,
            NOW,
            predecessor_fact_id=original.fact_id,
        )
    assert original.digest == original_digest
