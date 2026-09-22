import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_employee_attachment_packets import (
    build_attachment_packet,
    build_employee_packet,
)


def _write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value))
    return path


def test_employee_packet_requires_all_eight_and_never_infers_native_identity(
    tmp_path: Path,
) -> None:
    employees = [
        {
            "id": f"pro_{n}",
            "first_name": str(n),
            "last_name": "Person",
            "role": "field tech",
            "company_id": "company",
            "company_name": "All County",
        }
        for n in range(8)
    ]
    employees[7]["id"] = "pro_6b2b2b7177a54187a690cb198a6dbda5"
    employee_path = _write(
        tmp_path / "employees-page-0001.json",
        {"total_items": 8, "employees": employees},
    )
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    _write(
        jobs_root / "jobs-page-0001.json",
        {"jobs": [{"assigned_employees": [{"id": employees[7]["id"]}]}]},
    )
    prior_path = _write(
        tmp_path / "review.json",
        {
            "employees": {
                "records": [
                    {"hcp_native_id": f"pro_{n}", "relevant_assignments": n}
                    for n in range(7)
                ]
            }
        },
    )

    packet = build_employee_packet(
        employees_path=employee_path, jobs_root=jobs_root, prior_review_path=prior_path
    )

    assert packet["record_count"] == 8
    assert all(row["candidate_acp_employee_id"] is None for row in packet["records"])
    jason = next(
        row
        for row in packet["records"]
        if row["predecessor_disposition"] == "JASON_CALCI_ADDENDUM"
    )
    assert jason["refresh_assigned_job_count"] == 1


def test_attachment_packet_is_exact_and_fails_on_scope_drift(tmp_path: Path) -> None:
    open_work = _write(
        tmp_path / "open.json", [{"native_job_id": f"job_{n:03}"} for n in range(278)]
    )
    determination = _write(
        tmp_path / "determination.json",
        {"open_work_job_count": 278, "bounded_get_result": "HTTP_404_TEXT_HTML"},
    )
    packet = build_attachment_packet(
        open_work_path=open_work, determination_path=determination
    )
    assert packet["job_count"] == len(set(packet["job_source_ids"])) == 278
    assert packet["absence_is_authoritative"] is False

    _write(open_work, [{"native_job_id": "duplicate"}] * 278)
    with pytest.raises(ValueError, match="278 unique"):
        build_attachment_packet(
            open_work_path=open_work, determination_path=determination
        )
