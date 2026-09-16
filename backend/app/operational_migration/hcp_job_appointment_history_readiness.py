"""Seal exact SOURCE.4 Job and Appointment history readiness evidence.

This module classifies source graph completeness only.  It deliberately does
not infer native identities or authorize admission without a sanctioned native
binding snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-source4-job-appointment-history-readiness/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _verified_jobs(
    *, source_root: Path, collection: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    authority = collection["collections"]["jobs"]
    paths = sorted((source_root / "raw" / "jobs").glob("page-*.json"))
    expected = list(authority["page_sha256s"])
    if len(paths) != len(expected):
        raise ValueError("sealed Job page cardinality mismatch")
    jobs: dict[str, dict[str, Any]] = {}
    for path, expected_digest in zip(paths, expected):
        if _sha256(path) != expected_digest:
            raise ValueError(f"sealed Job page digest mismatch: {path.name}")
        for row in _load(path).get("jobs", []):
            source_id = row.get("id")
            if not source_id or source_id in jobs:
                raise ValueError("missing or duplicate sealed Job identity")
            jobs[source_id] = row
    if len(jobs) != authority["record_count"]:
        raise ValueError("sealed Job record count mismatch")
    return jobs


def _appointment_response_path(source_root: Path, artifact: dict[str, Any]) -> Path:
    job_hash = artifact["job_identity_sha256"]
    if artifact.get("effective_retry_sha256"):
        return source_root / "raw" / "job-appointments-retry" / f"{job_hash}.json"
    return source_root / "raw" / "job-appointments-2023-plus" / f"{job_hash}.json"


def build_readiness(*, source_root: Path) -> dict[str, object]:
    """Return deterministic, read-only Job/Appointment source readiness."""
    collection_path = source_root / "collection-manifest.json"
    acquisition_path = source_root / "acquisition-package-manifest.json"
    relationships_path = source_root / "relationship-appointments-manifest.json"
    collection = _load(collection_path)
    acquisition = _load(acquisition_path)
    relationships = _load(relationships_path)
    jobs = _verified_jobs(source_root=source_root, collection=collection)
    jobs_by_hash = {
        hashlib.sha256(source_id.encode()).hexdigest(): row
        for source_id, row in jobs.items()
    }

    job_records: list[dict[str, object]] = []
    job_counts: Counter[str] = Counter()
    for source_id, job in sorted(jobs.items()):
        customer_id = (job.get("customer") or {}).get("id")
        location_id = (job.get("address") or {}).get("id")
        if not customer_id:
            disposition = "CUSTOMER_SOURCE_MISSING"
        elif not location_id:
            disposition = "LOCATION_SOURCE_MISSING"
        else:
            disposition = "SOURCE_GRAPH_READY"
        technician_ids = sorted(
            {
                employee["id"]
                for employee in job.get("assigned_employees", [])
                if employee.get("id")
            }
        )
        job_counts[disposition] += 1
        job_records.append(
            {
                "source_job_id": source_id,
                "source_customer_id": customer_id,
                "source_location_id": location_id,
                "work_status": job.get("work_status"),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "cancelled_at": job.get("canceled_at"),
                "source_technician_ids": technician_ids,
                "technician_authority": "SOURCE_BACKED_NOT_NATIVE_BOUND",
                "source_graph_disposition": disposition,
                "native_admission_disposition": "BINDING_EVIDENCE_REQUIRED",
                "source_digest": _canonical_digest(job),
            }
        )

    appointment_records: list[dict[str, object]] = []
    appointment_counts: Counter[str] = Counter()
    relationship_counts: Counter[str] = Counter()
    seen_appointments: set[str] = set()
    for artifact in relationships["artifacts"]:
        job_hash = artifact["job_identity_sha256"]
        relationship_job = jobs_by_hash.get(job_hash)
        if relationship_job is None:
            raise ValueError("Appointment relationship references unknown Job")
        effective_digest = artifact.get("effective_retry_sha256")
        effective_status = 200 if effective_digest else artifact["http_status"]
        if effective_status != 200:
            relationship_counts["PROVIDER_RELATIONSHIP_ERROR"] += 1
            continue
        path = _appointment_response_path(source_root, artifact)
        expected_digest = effective_digest or artifact["response_sha256"]
        if not path.is_file() or _sha256(path) != expected_digest:
            raise ValueError(f"Appointment response custody mismatch: {job_hash}")
        appointments = _load(path).get("appointments", [])
        relationship_counts[
            "RELATIONSHIP_WITH_APPOINTMENTS"
            if appointments
            else "AUTHORITATIVE_EMPTY_RELATIONSHIP"
        ] += 1
        customer_id = (relationship_job.get("customer") or {}).get("id")
        location_id = (relationship_job.get("address") or {}).get("id")
        for appointment in appointments:
            source_id = appointment.get("id")
            if not source_id or source_id in seen_appointments:
                raise ValueError("missing or duplicate Appointment identity")
            seen_appointments.add(source_id)
            if not customer_id:
                disposition = "PARENT_CUSTOMER_SOURCE_MISSING"
            elif not location_id:
                disposition = "PARENT_LOCATION_SOURCE_MISSING"
            else:
                disposition = "SOURCE_GRAPH_READY"
            technician_ids = sorted(set(appointment.get("dispatched_employees_ids") or []))
            appointment_counts[disposition] += 1
            appointment_records.append(
                {
                    "source_appointment_id": source_id,
                    "source_job_id": relationship_job["id"],
                    "source_customer_id": customer_id,
                    "source_location_id": location_id,
                    "start_time": appointment.get("start_time"),
                    "end_time": appointment.get("end_time"),
                    "arrival_window_minutes": appointment.get("arrival_window_minutes"),
                    "anytime": appointment.get("anytime"),
                    "source_technician_ids": technician_ids,
                    "technician_authority": (
                        "SOURCE_BACKED_NOT_NATIVE_BOUND"
                        if technician_ids
                        else "SOURCE_UNASSIGNED"
                    ),
                    "source_graph_disposition": disposition,
                    "native_admission_disposition": "BINDING_EVIDENCE_REQUIRED",
                    "source_digest": _canonical_digest(appointment),
                }
            )

    if len(appointment_records) != relationships["appointment_record_count"]:
        raise ValueError("sealed Appointment record count mismatch")
    document: dict[str, object] = {
        "contract": CONTRACT,
        "source_system": "housecall_pro_source4",
        "mutation_authority": "none",
        "identity_matching": "EXACT_PROVIDER_IDS_ONLY",
        "source_package": {
            "acquisition_manifest_sha256": _sha256(acquisition_path),
            "acquisition_manifest_digest": acquisition["manifest_sha256"],
            "collection_manifest_sha256": _sha256(collection_path),
            "relationship_manifest_sha256": _sha256(relationships_path),
            "acquired_at": collection["acquisition_completed_at"],
        },
        "counts": {
            "jobs": {"total": len(job_records), **dict(sorted(job_counts.items()))},
            "appointments": {
                "total": len(appointment_records),
                **dict(sorted(appointment_counts.items())),
            },
            "appointment_relationships": dict(sorted(relationship_counts.items())),
        },
        "records": {"jobs": job_records, "appointments": appointment_records},
        "limitations": [
            "native admission requires sanctioned post-admission binding evidence",
            "source technician IDs are not native ACP Employee bindings",
            "provider relationship errors do not prove a Job has no Appointments",
            "missing Location source identity is never repaired by address matching",
        ],
    }
    document["digest"] = _canonical_digest(document)
    return document


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = build_readiness(source_root=args.source_root)
    args.output.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    )


if __name__ == "__main__":
    main()
