"""Execute gated read-only cross-domain acceptance over admitted projections."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from app.operational_measurement.post_source4_acceptance import (
    EstimateAcceptanceProjection,
    InvoiceARAcceptanceProjection,
    verify_cross_domain_chain,
)
from app.operational_measurement.realdata_acceptance import verify_operational_chain
from scripts.operational_realdata_acceptance import (
    _appointment,
    _crosswalk,
    _dispatch,
    _lineage,
    _schedule,
)


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(item in "0123456789abcdef" for item in value)


def _gates(payload: dict[str, Any]) -> bool:
    admission = payload.get("source4_admission")
    preview = payload.get("preview_clearance")
    return bool(
        isinstance(admission, dict)
        and admission.get("source_system") == "housecall_pro_source4"
        and admission.get("state") == "PLAN_CONFORMING"
        and _digest(admission.get("package_digest"))
        and _digest(admission.get("completion_evidence_digest"))
        and isinstance(preview, dict)
        and preview.get("state") == "CLEARED"
        and _digest(preview.get("authority_sha256"))
    )


def _estimate(value: dict[str, Any]) -> EstimateAcceptanceProjection:
    return EstimateAcceptanceProjection(
        source_id=value["source_id"], source_digest=value["source_digest"], source_job_id=value["source_job_id"],
        native_id=UUID(value["native_id"]) if value.get("native_id") else None,
        native_job_id=UUID(value["native_job_id"]) if value.get("native_job_id") else None,
        company_id=UUID(value["company_id"]), branch_id=UUID(value["branch_id"]),
        customer_id=UUID(value["customer_id"]) if value.get("customer_id") else None,
        service_location_id=UUID(value["service_location_id"]) if value.get("service_location_id") else None,
        status=value.get("status"), accepted_snapshot_digest=value.get("accepted_snapshot_digest"),
        native_evidence_digest=value.get("native_evidence_digest"),
    )


def _invoice(value: dict[str, Any]) -> InvoiceARAcceptanceProjection:
    return InvoiceARAcceptanceProjection(
        source_id=value["source_id"], source_digest=value["source_digest"], source_job_id=value["source_job_id"],
        source_estimate_id=value.get("source_estimate_id"), native_id=UUID(value["native_id"]) if value.get("native_id") else None,
        native_job_id=UUID(value["native_job_id"]) if value.get("native_job_id") else None,
        native_estimate_id=UUID(value["native_estimate_id"]) if value.get("native_estimate_id") else None,
        company_id=UUID(value["company_id"]), branch_id=UUID(value["branch_id"]),
        customer_id=UUID(value["customer_id"]) if value.get("customer_id") else None,
        service_location_id=UUID(value["service_location_id"]) if value.get("service_location_id") else None,
        currency=value.get("currency"), total_amount=Decimal(value["total_amount"]) if value.get("total_amount") is not None else None,
        open_amount=Decimal(value["open_amount"]) if value.get("open_amount") is not None else None,
        status=value.get("status"), line_evidence_complete=value.get("line_evidence_complete", False),
        native_evidence_digest=value.get("native_evidence_digest"),
    )


def run(input_path: Path, output_path: Path) -> int:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not _gates(payload):
        return 3
    company_id = UUID(payload["company_id"])
    branch_id = UUID(payload["branch_id"])
    operational = verify_operational_chain(
        tuple(_lineage(item) for item in payload.get("lineage", [])),
        tuple(_appointment(item) for item in payload.get("appointments", [])),
        tuple(_schedule(item) for item in payload.get("schedules", [])),
        tuple(_dispatch(item) for item in payload.get("dispatches", [])),
        company_id=company_id, branch_id=branch_id,
        crosswalks=tuple(_crosswalk(item) for item in payload.get("crosswalks", [])),
    )
    report = verify_cross_domain_chain(
        operational,
        tuple(_estimate(item) for item in payload.get("estimates", [])),
        tuple(_invoice(item) for item in payload.get("invoices", [])),
        company_id=company_id, branch_id=branch_id,
    )
    output_path.write_text(json.dumps(asdict(report), default=str, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    blocked = {"CONFLICTING", "MISSING_NATIVE", "ORPHANED"}
    return int(any(item in blocked for item in (*report.operational_counts, *report.commercial_counts)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        return run(args.input, args.output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        print("Cross-domain acceptance input is invalid.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
