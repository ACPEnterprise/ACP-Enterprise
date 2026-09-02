import json
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.operational_measurement.hcp_readiness import (
    NativeScheduleProjection,
    OperationalAppointmentEvidence,
    TechnicianCrosswalk,
)
from app.operational_measurement.realdata_acceptance import (
    MAX_RECORDS,
    AcceptanceClassification,
    DispatchAcceptanceProjection,
    OperationalDomain,
    OperationalLineageProjection,
    ParentLineage,
    verify_operational_chain,
)
from scripts.operational_realdata_acceptance import run

COMPANY = UUID("10000000-0000-0000-0000-000000000001")
OTHER_COMPANY = UUID("10000000-0000-0000-0000-000000000002")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
CUSTOMER = UUID("30000000-0000-0000-0000-000000000001")
LOCATION = UUID("40000000-0000-0000-0000-000000000001")
JOB = UUID("50000000-0000-0000-0000-000000000001")
APPOINTMENT = UUID("60000000-0000-0000-0000-000000000001")
EMPLOYEE = UUID("70000000-0000-0000-0000-000000000001")
START = datetime(2026, 9, 2, 13, tzinfo=timezone.utc)


def lineage() -> tuple[OperationalLineageProjection, ...]:
    customer = OperationalLineageProjection(
        OperationalDomain.CUSTOMER,
        "cus_source",
        "a" * 64,
        CUSTOMER,
        COMPANY,
        None,
        (),
        "b" * 64,
    )
    location = OperationalLineageProjection(
        OperationalDomain.SERVICE_LOCATION,
        "loc_source",
        "c" * 64,
        LOCATION,
        COMPANY,
        BRANCH,
        (ParentLineage(OperationalDomain.CUSTOMER, "cus_source", CUSTOMER),),
        "d" * 64,
    )
    job = OperationalLineageProjection(
        OperationalDomain.JOB,
        "job_source",
        "e" * 64,
        JOB,
        COMPANY,
        BRANCH,
        (
            ParentLineage(OperationalDomain.CUSTOMER, "cus_source", CUSTOMER),
            ParentLineage(
                OperationalDomain.SERVICE_LOCATION, "loc_source", LOCATION
            ),
        ),
        "f" * 64,
    )
    appointment = OperationalLineageProjection(
        OperationalDomain.APPOINTMENT,
        "appt_source",
        "1" * 64,
        APPOINTMENT,
        COMPANY,
        BRANCH,
        (
            ParentLineage(OperationalDomain.CUSTOMER, "cus_source", CUSTOMER),
            ParentLineage(
                OperationalDomain.SERVICE_LOCATION, "loc_source", LOCATION
            ),
            ParentLineage(OperationalDomain.JOB, "job_source", JOB),
        ),
        "2" * 64,
    )
    return customer, location, job, appointment


def source_appointment(**changes: object) -> OperationalAppointmentEvidence:
    values = {
        "source_id": "appt_source",
        "source_digest": "1" * 64,
        "source_job_id": "job_source",
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "service_location_id": LOCATION,
        "status": "scheduled",
        "window_start_at": START,
        "window_end_at": START + timedelta(hours=2),
        "scheduled_duration_minutes": 120,
        "source_technician_ids": ("tech_source",),
        "parent_admitted": True,
    }
    values.update(changes)
    return OperationalAppointmentEvidence(**values)  # type: ignore[arg-type]


def schedule(**changes: object) -> NativeScheduleProjection:
    values = {
        "source_appointment_id": "appt_source",
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "status": "scheduled",
        "window_start_at": START,
        "window_end_at": START + timedelta(hours=2),
        "employee_ids": (EMPLOYEE,),
        "evidence_digest": "3" * 64,
    }
    values.update(changes)
    return NativeScheduleProjection(**values)  # type: ignore[arg-type]


def dispatch(**changes: object) -> DispatchAcceptanceProjection:
    values = {
        "source_appointment_id": "appt_source",
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "status": "scheduled",
        "window_start_at": START,
        "window_end_at": START + timedelta(hours=2),
        "employee_ids": (EMPLOYEE,),
        "evidence_digest": "4" * 64,
    }
    values.update(changes)
    return DispatchAcceptanceProjection(**values)  # type: ignore[arg-type]


def crosswalk() -> TechnicianCrosswalk:
    return TechnicianCrosswalk("tech_source", EMPLOYEE, True, "5" * 64)


def report(
    *,
    lineage_records: tuple[OperationalLineageProjection, ...] | None = None,
    source_records: tuple[OperationalAppointmentEvidence, ...] | None = None,
    schedules: tuple[NativeScheduleProjection, ...] | None = None,
    dispatches: tuple[DispatchAcceptanceProjection, ...] | None = None,
):
    return verify_operational_chain(
        lineage() if lineage_records is None else lineage_records,
        (source_appointment(),) if source_records is None else source_records,
        (schedule(),) if schedules is None else schedules,
        (dispatch(),) if dispatches is None else dispatches,
        company_id=COMPANY,
        branch_id=BRANCH,
        crosswalks=(crosswalk(),),
    )


def test_complete_chain_and_schedule_dispatch_projection_match() -> None:
    result = report()
    assert result.contract_version == "operations.realdata.acceptance.v1"
    assert result.counts == {"MATCHED": 5}
    assert result.source_record_count == 4
    assert result.appointment_count == 1
    assert result.mutation_authority == "none"


def test_report_is_deterministic_under_input_reordering() -> None:
    first = report()
    replay = report(lineage_records=tuple(reversed(lineage())))
    assert replay.findings == first.findings
    assert replay.evidence_digest == first.evidence_digest


def test_missing_native_and_orphan_relationships_fail_closed() -> None:
    customer, location, job, appointment = lineage()
    missing_location = OperationalLineageProjection(
        location.domain,
        location.source_id,
        location.source_digest,
        None,
        location.company_id,
        location.branch_id,
        location.parents,
        None,
    )
    result = report(
        lineage_records=(customer, missing_location, job, appointment), schedules=()
    )
    by_identity = {
        (item.stage, item.domain, item.source_id): item for item in result.findings
    }
    assert (
        by_identity[("LINEAGE", "SERVICE_LOCATION", "loc_source")].classification
        is AcceptanceClassification.MISSING_NATIVE
    )
    assert (
        by_identity[("LINEAGE", "JOB", "job_source")].classification
        is AcceptanceClassification.ORPHANED
    )
    assert (
        by_identity[("OPERATIONAL_PROJECTION", "APPOINTMENT", "appt_source")]
        .classification
        is AcceptanceClassification.MISSING_NATIVE
    )


@pytest.mark.parametrize(
    ("dispatch_change", "condition"),
    [
        ({"status": "completed"}, "SCHEDULE_DISPATCH_STATUS_DISAGREEMENT"),
        (
            {"window_start_at": START + timedelta(hours=1)},
            "SCHEDULE_DISPATCH_WINDOW_DISAGREEMENT",
        ),
        ({"employee_ids": ()}, "SCHEDULE_DISPATCH_TECHNICIAN_DISAGREEMENT"),
        ({"company_id": OTHER_COMPANY}, "SCHEDULE_DISPATCH_SCOPE_DISAGREEMENT"),
    ],
)
def test_schedule_dispatch_disagreement_is_conflicting(
    dispatch_change: dict[str, object], condition: str
) -> None:
    result = report(dispatches=(dispatch(**dispatch_change),))
    finding = next(item for item in result.findings if item.stage == "OPERATIONAL_PROJECTION")
    assert finding.classification is AcceptanceClassification.CONFLICTING
    assert condition in finding.conditions


def test_unmapped_technician_remains_partial_not_fabricated() -> None:
    result = verify_operational_chain(
        lineage(),
        (source_appointment(source_technician_ids=("unknown",)),),
        (schedule(employee_ids=()),),
        (dispatch(employee_ids=()),),
        company_id=COMPANY,
        branch_id=BRANCH,
    )
    projection = next(item for item in result.findings if item.stage == "OPERATIONAL_PROJECTION")
    assert projection.classification is AcceptanceClassification.PARTIAL
    assert projection.conditions == ("TECHNICIAN_MAPPING_INCOMPLETE",)


def test_admitted_appointment_relationship_mismatch_is_conflicting() -> None:
    result = report(
        source_records=(
            source_appointment(
                source_job_id="another_job",
                customer_id=UUID("30000000-0000-0000-0000-000000000009"),
            ),
        )
    )
    projection = next(
        item for item in result.findings if item.stage == "OPERATIONAL_PROJECTION"
    )
    assert projection.classification is AcceptanceClassification.CONFLICTING
    assert {
        "CUSTOMER_RELATIONSHIP_CONFLICT",
        "JOB_RELATIONSHIP_CONFLICT",
    } <= set(projection.conditions)


def test_duplicate_lineage_and_foreign_scope_are_conflicting() -> None:
    records = lineage()
    foreign = OperationalLineageProjection(
        records[0].domain,
        records[0].source_id,
        "9" * 64,
        UUID("30000000-0000-0000-0000-000000000009"),
        OTHER_COMPANY,
        None,
        (),
        "8" * 64,
    )
    result = report(lineage_records=(*records, foreign))
    customer = next(
        item
        for item in result.findings
        if item.domain == "CUSTOMER" and item.source_id == "cus_source"
    )
    assert customer.classification is AcceptanceClassification.CONFLICTING
    assert customer.conditions == ("DUPLICATE_NATIVE_SOURCE_IDENTITY",)


def test_contract_is_bounded_and_immutable() -> None:
    with pytest.raises(ValueError, match="exceeds its bound"):
        verify_operational_chain(
            tuple(lineage()[0] for _ in range(MAX_RECORDS + 1)),
            (),
            (),
            (),
            company_id=COMPANY,
            branch_id=BRANCH,
        )
    with pytest.raises(FrozenInstanceError):
        report().mutation_authority = "write"  # type: ignore[misc]


def test_cli_consumes_an_admitted_projection_bundle(tmp_path) -> None:
    input_path = tmp_path / "admitted-projections.json"
    output_path = tmp_path / "acceptance-report.json"
    payload = {
        "company_id": str(COMPANY),
        "branch_id": str(BRANCH),
        "lineage": [asdict(item) for item in lineage()],
        "appointments": [asdict(source_appointment())],
        "schedules": [asdict(schedule())],
        "dispatches": [asdict(dispatch())],
        "crosswalks": [asdict(crosswalk())],
    }
    input_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    assert run(input_path, output_path) == 0
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["counts"] == {"MATCHED": 5}
    assert result["mutation_authority"] == "none"
