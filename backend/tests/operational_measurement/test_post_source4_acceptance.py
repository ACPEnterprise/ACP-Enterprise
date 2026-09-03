import json
from dataclasses import FrozenInstanceError, asdict, replace
from decimal import Decimal
from uuid import UUID

import pytest

from app.operational_measurement.post_source4_acceptance import (
    MAX_COMMERCIAL_RECORDS,
    EstimateAcceptanceProjection,
    InvoiceARAcceptanceProjection,
    verify_cross_domain_chain,
)
from app.operational_measurement.realdata_acceptance import AcceptanceClassification
from scripts.crossdomain_post_source4_acceptance import main, run
from tests.operational_measurement.test_realdata_acceptance import (
    BRANCH,
    COMPANY,
    CUSTOMER,
    JOB,
    LOCATION,
    crosswalk,
    dispatch,
    lineage,
    schedule,
    source_appointment,
)
from tests.operational_measurement.test_realdata_acceptance import (
    report as operational_report,
)

ESTIMATE = UUID("80000000-0000-0000-0000-000000000001")
INVOICE = UUID("90000000-0000-0000-0000-000000000001")


def estimate(**changes: object) -> EstimateAcceptanceProjection:
    values = {
        "source_id": "estimate_source",
        "source_digest": "6" * 64,
        "source_job_id": "job_source",
        "native_id": ESTIMATE,
        "native_job_id": JOB,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "service_location_id": LOCATION,
        "status": "accepted",
        "accepted_snapshot_digest": "7" * 64,
        "native_evidence_digest": "8" * 64,
    }
    values.update(changes)
    return EstimateAcceptanceProjection(**values)  # type: ignore[arg-type]


def invoice(**changes: object) -> InvoiceARAcceptanceProjection:
    values = {
        "source_id": "invoice_source",
        "source_digest": "9" * 64,
        "source_job_id": "job_source",
        "source_estimate_id": "estimate_source",
        "native_id": INVOICE,
        "native_job_id": JOB,
        "native_estimate_id": ESTIMATE,
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "customer_id": CUSTOMER,
        "service_location_id": LOCATION,
        "currency": "USD",
        "total_amount": Decimal("850.00"),
        "open_amount": Decimal("850.00"),
        "status": "issued",
        "line_evidence_complete": True,
        "native_evidence_digest": "a" * 64,
    }
    values.update(changes)
    return InvoiceARAcceptanceProjection(**values)  # type: ignore[arg-type]


def verify(*, estimates=None, invoices=None, operational=None):
    return verify_cross_domain_chain(
        operational or operational_report(),
        (estimate(),) if estimates is None else estimates,
        (invoice(),) if invoices is None else invoices,
        company_id=COMPANY,
        branch_id=BRANCH,
    )


def test_complete_customer_through_invoice_ar_chain_is_deterministic() -> None:
    first = verify()
    replay = verify()
    assert first.contract_version == "operations.crossdomain.post-source4.acceptance.v1"
    assert first.operational_counts == {"MATCHED": 5}
    assert first.commercial_counts == {"MATCHED": 2}
    assert replay.evidence_digest == first.evidence_digest
    assert first.mutation_authority == "none"
    with pytest.raises(FrozenInstanceError):
        first.mutation_authority = "write"  # type: ignore[misc]


def test_partial_source_evidence_and_unmapped_technician_are_not_fabricated() -> None:
    operational = operational_report(
        source_records=(source_appointment(source_technician_ids=("unmapped",)),),
        schedules=(schedule(employee_ids=()),),
        dispatches=(dispatch(employee_ids=()),),
    )
    result = verify(
        operational=operational,
        estimates=(estimate(accepted_snapshot_digest=None),),
        invoices=(invoice(line_evidence_complete=False),),
    )
    assert result.operational_counts == {"MATCHED": 4, "PARTIAL": 1}
    assert result.commercial_counts == {"PARTIAL": 2}


@pytest.mark.parametrize(
    "changed,condition",
    [
        ({"company_id": UUID("10000000-0000-0000-0000-000000000099")}, "COMPANY_OR_BRANCH_SCOPE_CONFLICT"),
        ({"native_job_id": UUID("50000000-0000-0000-0000-000000000099")}, "JOB_RELATIONSHIP_CONFLICT"),
        ({"open_amount": Decimal("851.00")}, "OPEN_BALANCE_EXCEEDS_INVOICE"),
    ],
)
def test_scope_relationship_and_ar_conflicts_fail_closed(changed, condition) -> None:
    result = verify(invoices=(invoice(**changed),))
    finding = result.commercial_findings[1]
    assert finding.classification is AcceptanceClassification.CONFLICTING
    assert condition in finding.conditions


def test_stale_duplicate_and_missing_lineage_fail_closed() -> None:
    duplicate = replace(invoice(), source_digest="b" * 64)
    result = verify(invoices=(invoice(), duplicate))
    assert result.commercial_findings[1].conditions == ("DUPLICATE_NATIVE_SOURCE_IDENTITY",)
    orphan = verify(estimates=(estimate(source_job_id="missing_job"),), invoices=())
    assert orphan.commercial_findings[0].classification is AcceptanceClassification.ORPHANED


def test_commercial_input_is_bounded() -> None:
    with pytest.raises(ValueError, match="exceeds its bound"):
        verify(estimates=tuple(estimate() for _ in range(MAX_COMMERCIAL_RECORDS + 1)), invoices=())


def test_cli_requires_both_admission_and_preview_clearance(tmp_path) -> None:
    input_path = tmp_path / "admitted.json"
    output_path = tmp_path / "report.json"
    payload = {
        "company_id": str(COMPANY), "branch_id": str(BRANCH),
        "lineage": [asdict(item) for item in lineage()],
        "appointments": [asdict(source_appointment())], "schedules": [asdict(schedule())],
        "dispatches": [asdict(dispatch())], "crosswalks": [asdict(crosswalk())],
        "estimates": [asdict(estimate())], "invoices": [asdict(invoice())],
    }
    input_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    assert run(input_path, output_path) == 3
    assert not output_path.exists()
    payload["source4_admission"] = {"source_system": "housecall_pro_source4", "state": "PLAN_CONFORMING", "package_digest": "c" * 64, "completion_evidence_digest": "d" * 64}
    payload["preview_clearance"] = {"state": "CLEARED", "authority_sha256": "e" * 64}
    input_path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    assert run(input_path, output_path) == 0
    assert json.loads(output_path.read_text())["commercial_counts"] == {"MATCHED": 2}


def test_cli_projects_malformed_input_as_a_safe_fixed_error(tmp_path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "invalid.json"
    output_path = tmp_path / "report.json"
    canary = "protected-customer-canary"
    input_path.write_text(f'{{"secret":"{canary}"', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["acceptance", "--input", str(input_path), "--output", str(output_path)])
    assert main() == 2
    captured = capsys.readouterr()
    assert captured.err.strip() == "Cross-domain acceptance input is invalid."
    assert canary not in captured.err
    assert not output_path.exists()
