"""Run read-only operational acceptance over an admitted projection bundle."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.operational_measurement.hcp_readiness import (
    NativeScheduleProjection,
    OperationalAppointmentEvidence,
    TechnicianCrosswalk,
)
from app.operational_measurement.realdata_acceptance import (
    DispatchAcceptanceProjection,
    OperationalDomain,
    OperationalLineageProjection,
    ParentLineage,
    verify_operational_chain,
)


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _lineage(value: dict[str, Any]) -> OperationalLineageProjection:
    return OperationalLineageProjection(
        domain=OperationalDomain(value["domain"]),
        source_id=value["source_id"],
        source_digest=value["source_digest"],
        native_id=_uuid(value.get("native_id")),
        company_id=UUID(value["company_id"]),
        branch_id=_uuid(value.get("branch_id")),
        parents=tuple(
            ParentLineage(
                OperationalDomain(parent["domain"]),
                parent["source_id"],
                _uuid(parent.get("native_id")),
            )
            for parent in value.get("parents", [])
        ),
        native_evidence_digest=value.get("native_evidence_digest"),
    )


def _appointment(value: dict[str, Any]) -> OperationalAppointmentEvidence:
    return OperationalAppointmentEvidence(
        source_id=value["source_id"],
        source_digest=value["source_digest"],
        source_job_id=value["source_job_id"],
        company_id=UUID(value["company_id"]),
        branch_id=UUID(value["branch_id"]),
        customer_id=_uuid(value.get("customer_id")),
        service_location_id=_uuid(value.get("service_location_id")),
        status=value["status"],
        window_start_at=_datetime(value.get("window_start_at")),
        window_end_at=_datetime(value.get("window_end_at")),
        scheduled_duration_minutes=value.get("scheduled_duration_minutes"),
        source_technician_ids=tuple(value.get("source_technician_ids", [])),
        parent_admitted=value["parent_admitted"],
        migration_held=value.get("migration_held", False),
    )


def _schedule(value: dict[str, Any]) -> NativeScheduleProjection:
    return NativeScheduleProjection(
        source_appointment_id=value["source_appointment_id"],
        company_id=UUID(value["company_id"]),
        branch_id=UUID(value["branch_id"]),
        status=value["status"],
        window_start_at=_datetime(value.get("window_start_at")),
        window_end_at=_datetime(value.get("window_end_at")),
        employee_ids=tuple(UUID(item) for item in value.get("employee_ids", [])),
        evidence_digest=value["evidence_digest"],
    )


def _dispatch(value: dict[str, Any]) -> DispatchAcceptanceProjection:
    return DispatchAcceptanceProjection(
        source_appointment_id=value["source_appointment_id"],
        company_id=UUID(value["company_id"]),
        branch_id=UUID(value["branch_id"]),
        status=value["status"],
        window_start_at=_datetime(value.get("window_start_at")),
        window_end_at=_datetime(value.get("window_end_at")),
        employee_ids=tuple(UUID(item) for item in value.get("employee_ids", [])),
        evidence_digest=value["evidence_digest"],
    )


def _crosswalk(value: dict[str, Any]) -> TechnicianCrosswalk:
    return TechnicianCrosswalk(
        source_technician_id=value["source_technician_id"],
        employee_id=_uuid(value.get("employee_id")),
        employee_active=value.get("employee_active"),
        evidence_digest=value["evidence_digest"],
    )


def run(input_path: Path, output_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    report = verify_operational_chain(
        tuple(_lineage(item) for item in payload.get("lineage", [])),
        tuple(_appointment(item) for item in payload.get("appointments", [])),
        tuple(_schedule(item) for item in payload.get("schedules", [])),
        tuple(_dispatch(item) for item in payload.get("dispatches", [])),
        company_id=UUID(payload["company_id"]),
        branch_id=_uuid(payload.get("branch_id")),
        crosswalks=tuple(_crosswalk(item) for item in payload.get("crosswalks", [])),
    )
    output_path.write_text(
        json.dumps(asdict(report), default=str, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return int(
        any(
            item in report.counts
            for item in ("CONFLICTING", "MISSING_NATIVE", "ORPHANED")
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
