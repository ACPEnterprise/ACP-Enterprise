from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.dispatch.intelligence import TimeWindow
from app.operational_measurement.hcp_readiness import (
    MAX_BATCH_SIZE,
    DateDisposition,
    DurationCandidateClass,
    OperationalAppointmentEvidence,
    OperationalJobEvidence,
    ReadinessState,
    TechnicianCrosswalk,
    TechnicianMappingState,
    adapt_migration_appointment,
    adapt_migration_job,
    classify_duration,
    data_quality_conditions,
    dispatch_readiness,
    economics_operational_readiness,
    luminary_readiness_explanations,
    measured_duration_evidence,
    reconcile_date,
    source_field_audit,
    technician_mapping,
    validate_window,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
CUSTOMER = UUID("30000000-0000-0000-0000-000000000001")
LOCATION = UUID("40000000-0000-0000-0000-000000000001")
EMPLOYEE = UUID("50000000-0000-0000-0000-000000000001")
DIGEST = "a" * 64
START = datetime(2026, 8, 28, 13, tzinfo=timezone.utc)


def appointment(**changes: object) -> OperationalAppointmentEvidence:
    values = {
        "source_id": "appt_synthetic_1",
        "source_digest": DIGEST,
        "source_job_id": "job_synthetic_1",
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "service_location_id": LOCATION,
        "status": "scheduled",
        "window_start_at": START,
        "window_end_at": START + timedelta(hours=2),
        "scheduled_duration_minutes": 120,
        "source_technician_ids": ("pro_synthetic_1",),
        "parent_admitted": True,
    }
    values.update(changes)
    return OperationalAppointmentEvidence(**values)  # type: ignore[arg-type]


def job(**changes: object) -> OperationalJobEvidence:
    values = {
        "source_id": "job_synthetic_1",
        "source_digest": DIGEST,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "service_location_id": LOCATION,
        "status": "completed",
        "scheduled_start_at": START,
        "scheduled_end_at": START + timedelta(hours=2),
        "started_at": START + timedelta(minutes=10),
        "completed_at": START + timedelta(minutes=100),
        "service_category": "synthetic_service",
        "source_technician_ids": ("pro_synthetic_1",),
    }
    values.update(changes)
    return OperationalJobEvidence(**values)  # type: ignore[arg-type]


def crosswalk(*, active: bool = True) -> TechnicianCrosswalk:
    return TechnicianCrosswalk("pro_synthetic_1", EMPLOYEE, active, "b" * 64)


def test_sanctioned_migration_records_adapt_without_source_access() -> None:
    source_job = JobMigrationRecord(
        source_id="job_synthetic_1",
        source_customer_id="cus_synthetic_1",
        source_service_location_id="adr_synthetic_1",
        status="completed",
        started_at=START,
        completed_at=START + timedelta(hours=1),
        assigned_technician_source_ids=("pro_synthetic_1",),
        external_metadata={"source_digest": DIGEST},
    )
    source_appointment = AppointmentMigrationRecord(
        source_id="appt_synthetic_1",
        source_job_id=source_job.source_id,
        source_customer_id=source_job.source_customer_id,
        source_service_location_id=source_job.source_service_location_id,
        status="completed",
        arrival_window_start_at=START,
        arrival_window_end_at=START + timedelta(hours=2),
        duration_minutes=120,
        assigned_technician_source_ids=("pro_synthetic_1",),
        external_metadata={"source_digest": DIGEST},
    )
    admitted_job = adapt_migration_job(
        source_job,
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_id=CUSTOMER,
        service_location_id=LOCATION,
    )
    admitted_appointment = adapt_migration_appointment(
        source_appointment,
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_id=CUSTOMER,
        service_location_id=LOCATION,
        parent_admitted=True,
    )
    assert admitted_job.source_digest == DIGEST
    assert admitted_appointment.source_job_id == admitted_job.source_id


def test_adapters_reject_missing_or_unbound_source_digest() -> None:
    source_job = JobMigrationRecord(
        source_id="job_synthetic_1",
        source_customer_id="cus_synthetic_1",
        source_service_location_id="adr_synthetic_1",
        status="scheduled",
    )
    with pytest.raises(ValueError, match="SHA-256"):
        adapt_migration_job(
            source_job,
            company_id=COMPANY,
            branch_id=BRANCH,
            customer_id=CUSTOMER,
            service_location_id=LOCATION,
        )


def test_field_audit_is_explicit_about_admitted_and_dropped_source_semantics() -> None:
    fields = {item.field: item for item in source_field_audit()}
    assert fields["scheduled_window"].state is ReadinessState.AVAILABLE
    assert fields["arrival_timestamp"].state is ReadinessState.PARTIAL
    assert fields["pause_resume"].state is ReadinessState.ABSENT
    assert fields["service_category"].state is ReadinessState.PARTIAL
    assert fields["priority"].state is ReadinessState.SOURCE_REQUIRED


def test_window_validation_never_invents_time_and_handles_cross_midnight() -> None:
    assert (
        validate_window(None, None, accepted_timezone="America/New_York").state
        is ReadinessState.ABSENT
    )
    assert (
        validate_window(START, START, accepted_timezone="America/New_York").state
        is ReadinessState.CONFLICTING
    )
    naive = START.replace(tzinfo=None)
    assert validate_window(
        naive, naive + timedelta(hours=1), accepted_timezone="America/New_York"
    ).conditions == ("TIMEZONE_MISSING",)
    overnight = validate_window(
        datetime(2026, 8, 29, 3, tzinfo=timezone.utc),
        datetime(2026, 8, 29, 6, tzinfo=timezone.utc),
        accepted_timezone="America/New_York",
    )
    assert "WINDOW_CROSSES_MIDNIGHT" in overnight.conditions


def test_duration_requires_pause_corrected_evidence_for_active_measurement() -> None:
    partial = classify_duration(job(), appointment())
    assert partial.classification is DurationCandidateClass.PARTIAL_DURATION_EVIDENCE
    assert partial.elapsed_work_minutes == 90
    with pytest.raises(ValueError, match="qualified active duration"):
        measured_duration_evidence(job(), partial)

    pause = TimeWindow(START + timedelta(minutes=30), START + timedelta(minutes=45))
    qualified_job = job(pause_intervals=(pause,))
    qualified = classify_duration(qualified_job, appointment())
    assert (
        qualified.classification is DurationCandidateClass.QUALIFIED_MEASURED_DURATION
    )
    assert qualified.active_minutes == 75
    assert measured_duration_evidence(qualified_job, qualified).active_minutes == 75


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        (
            {"started_at": None, "completed_at": None},
            DurationCandidateClass.SCHEDULED_DURATION_ONLY,
        ),
        ({"started_at": None}, DurationCandidateClass.PARTIAL_DURATION_EVIDENCE),
        ({"completed_at": START}, DurationCandidateClass.INVALID_DURATION),
    ],
)
def test_duration_candidate_dispositions(changes, expected) -> None:
    assert classify_duration(job(**changes), appointment()).classification is expected


def test_technician_mapping_preserves_historical_inactive_and_multiple_work() -> None:
    assert (
        technician_mapping(("pro_synthetic_1",), (crosswalk(active=False),)).state
        is TechnicianMappingState.MAPPED_HISTORICAL_INACTIVE
    )
    unresolved = technician_mapping(("pro_unknown",), ())
    assert unresolved.state is TechnicianMappingState.UNMAPPED
    assert unresolved.unresolved_source_ids == ("pro_unknown",)
    multiple = technician_mapping(("pro_synthetic_1", "pro_unknown"), (crosswalk(),))
    assert multiple.state is TechnicianMappingState.UNMAPPED


def test_august_28_reconciliation_accounts_for_every_source_identity() -> None:
    records = (
        appointment(),
        appointment(source_id="appt_unmapped", source_technician_ids=("pro_unknown",)),
        appointment(source_id="appt_missing", window_start_at=None, window_end_at=None),
        appointment(source_id="appt_cancelled", status="cancelled"),
        appointment(source_id="appt_held", migration_held=True),
        appointment(
            source_id="appt_other",
            window_start_at=START + timedelta(days=1),
            window_end_at=START + timedelta(days=1, hours=1),
        ),
    )
    report = reconcile_date(
        records,
        local_date=date(2026, 8, 28),
        timezone_name="America/New_York",
        crosswalks=(crosswalk(),),
    )
    assert report.reconciliation_delta == 0
    assert set(report.disposition_counts) == {item.value for item in DateDisposition}
    assert report.source_count == 6
    replay = reconcile_date(
        records,
        local_date=date(2026, 8, 28),
        timezone_name="America/New_York",
        crosswalks=(crosswalk(),),
    )
    assert replay.evidence_digest == report.evidence_digest


def test_dispatch_and_luminary_remain_truthful_when_context_is_missing() -> None:
    readiness = dispatch_readiness(appointment(), crosswalks=())
    assert "customer_window" in readiness.admitted_constraints
    assert {
        "travel",
        "fleet",
        "capability",
        "certification",
        "technician_mapping",
    } <= set(readiness.unknown_constraints)
    explanations = luminary_readiness_explanations(
        scheduled=True,
        technician_mapped=False,
        duration=DurationCandidateClass.PARTIAL_DURATION_EVIDENCE,
        category_available=False,
        economics_complete=False,
    )
    assert any("Economics remains incomplete" in item for item in explanations)
    assert not any(
        "revenue" in item.lower() and "inferred" not in item.lower()
        for item in explanations
    )


def test_economics_admits_dimensions_but_never_infers_money() -> None:
    duration = classify_duration(job(), appointment())
    readiness = economics_operational_readiness(job(service_category=None), duration)
    assert readiness.state is ReadinessState.PARTIAL
    assert "work_period" in readiness.admissible_dimensions
    assert {"service_category", "measured_active_duration"} <= set(
        readiness.missing_dimensions
    )
    assert set(readiness.prohibited_inferences) == {
        "revenue",
        "cash",
        "labor_cost",
        "material_cost",
        "profitability",
    }


def test_data_quality_reports_source_gaps_without_repairing_them() -> None:
    records = (
        appointment(
            source_job_id="missing_job",
            customer_id=None,
            service_location_id=None,
            window_start_at=None,
            window_end_at=None,
            source_technician_ids=(),
            parent_admitted=False,
        ),
    )
    conditions = data_quality_conditions(
        (job(service_category=None),),
        records,
        accepted_timezone="America/New_York",
    )
    codes = {item.code for item in conditions}
    assert {
        "UNKNOWN_CATEGORY",
        "MISSING_DURATION_EVIDENCE",
        "MISSING_JOB",
        "MISSING_CUSTOMER",
        "MISSING_LOCATION",
        "WINDOW_MISSING",
        "UNMAPPED_TECHNICIAN",
    } <= codes


def test_data_quality_detects_contradictory_duplicate_source_identity() -> None:
    conditions = data_quality_conditions(
        (),
        (appointment(), appointment(source_digest="b" * 64)),
        accepted_timezone="America/New_York",
    )
    assert any(
        item.code == "DUPLICATE_SOURCE_IDENTITY"
        and item.state is ReadinessState.CONFLICTING
        for item in conditions
    )


def test_data_quality_fails_closed_on_conflicting_lifecycle() -> None:
    conditions = data_quality_conditions(
        (job(status="cancelled"),),
        (appointment(status="completed"),),
        accepted_timezone="America/New_York",
        crosswalks=(crosswalk(),),
    )
    assert any(
        item.code == "CONFLICTING_LIFECYCLE"
        and item.state is ReadinessState.CONFLICTING
        for item in conditions
    )


def test_batch_limit_fails_closed() -> None:
    with pytest.raises(ValueError, match="batch exceeds"):
        reconcile_date(
            tuple(
                appointment(source_id=f"appt_{index}")
                for index in range(MAX_BATCH_SIZE + 1)
            ),
            local_date=date(2026, 8, 28),
            timezone_name="America/New_York",
        )
