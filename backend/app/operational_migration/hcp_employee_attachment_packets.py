"""Build bounded, non-mutating HCP employee and attachment review packets."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EMPLOYEE_CONTRACT = "hcp-employee-owner-certification/v1"
ATTACHMENT_CONTRACT = "hcp-open-work-attachment-export-request/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        rows.extend(json.loads(path.read_bytes())[key])
    return rows


def build_employee_packet(
    *, employees_path: Path, jobs_root: Path, prior_review_path: Path
) -> dict[str, Any]:
    source = json.loads(employees_path.read_bytes())
    employees = source["employees"]
    if source["total_items"] != 8 or len(employees) != 8:
        raise ValueError("expected the exact eight-employee refresh")

    prior = json.loads(prior_review_path.read_bytes())["employees"]["records"]
    prior_by_id = {row["hcp_native_id"]: row for row in prior}
    if len(prior_by_id) != 7:
        raise ValueError("expected the accepted seven-employee predecessor packet")

    assignments: Counter[str] = Counter()
    for job in _pages(jobs_root, "jobs", "jobs"):
        assignments.update(row["id"] for row in job.get("assigned_employees", []))

    records = []
    for employee in sorted(employees, key=lambda row: row["id"]):
        source_id = employee["id"]
        predecessor = prior_by_id.get(source_id)
        records.append(
            {
                "hcp_employee_source_id": source_id,
                "source_name": " ".join(
                    value for value in (employee["first_name"], employee["last_name"]) if value
                ),
                "source_role": employee.get("role"),
                "source_company_id": employee["company_id"],
                "source_company_name": employee["company_name"],
                "branch": None,
                "branch_evidence": "OWNER_CERTIFICATION_REQUIRED",
                "refresh_assigned_job_count": assignments[source_id],
                "predecessor_relevant_assignment_count": (
                    predecessor["relevant_assignments"] if predecessor else None
                ),
                "predecessor_disposition": (
                    "OWNER_DISPOSITION_RECORDED" if predecessor else "JASON_CALCI_ADDENDUM"
                ),
                "candidate_acp_employee_id": None,
                "classification": "OWNER_CERTIFICATION_REQUIRED",
                "action_required": (
                    "Certify non-human exclusion and held assignment policy"
                    if source_id == "pro_4b6e26c209ad4702a2e0512ba2a0b5ba"
                    else "Certify exact ACP Employee identity or authorize candidate creation, and certify Branch"
                ),
            }
        )

    return {
        "contract": EMPLOYEE_CONTRACT,
        "mutation_authority": "none",
        "identity_resolution": "exact_source_ids_only_no_heuristics",
        "employees_file_sha256": _sha256(employees_path),
        "prior_review_file_sha256": _sha256(prior_review_path),
        "record_count": len(records),
        "records": records,
    }


def build_attachment_packet(
    *, open_work_path: Path, determination_path: Path
) -> dict[str, Any]:
    open_work = json.loads(open_work_path.read_bytes())
    determination = json.loads(determination_path.read_bytes())
    job_ids = sorted(row["native_job_id"] for row in open_work)
    if len(job_ids) != 278 or len(set(job_ids)) != 278:
        raise ValueError("expected 278 unique open-work Job identities")
    if determination["open_work_job_count"] != 278:
        raise ValueError("attachment determination scope mismatch")
    return {
        "contract": ATTACHMENT_CONTRACT,
        "mutation_authority": "none",
        "scope": "exact_278_open_work_jobs",
        "open_work_file_sha256": _sha256(open_work_path),
        "determination_file_sha256": _sha256(determination_path),
        "job_count": 278,
        "job_source_ids": job_ids,
        "acquired_attachment_metadata_count": 0,
        "acquired_content_object_count": 0,
        "public_api_result": determination["bounded_get_result"],
        "absence_is_authoritative": False,
        "provider_request": {
            "method": "HCP_UI_OR_SUPPORT_EXPORT",
            "required_metadata": [
                "parent_job_source_id",
                "artifact_identity_or_reference",
                "filename",
                "content_type",
                "byte_size",
                "created_at",
                "author_when_available",
            ],
            "content_rule": "retrieve only owner-designated continuity-critical content",
            "custody_rule": "seal every received file with SHA-256 in protected storage",
        },
    }
