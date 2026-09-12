"""Build the private, record-level September HCP overlay packet without mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayKey,
    OverlayRecord,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        rows.extend(_load(path)[key])
    return rows


def _index(refresh: Path, schedule: Path) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[OverlayKey, ...]]]:
    customers = _pages(refresh, "customers", "customers")
    jobs = _pages(refresh, "jobs", "jobs")
    values: dict[str, dict[str, Any]] = {}
    parents: dict[str, tuple[OverlayKey, ...]] = {}
    for customer in customers:
        customer_id = customer["id"]
        values[f"customer:{customer_id}"] = customer
        for location in customer.get("addresses", []):
            if location.get("id"):
                values[f"service_location:{location['id']}"] = location
                parents[f"service_location:{location['id']}"] = (
                    OverlayKey("customer", customer_id),
                )
    jobs_by_hash: dict[str, str] = {}
    for job in jobs:
        job_id = job["id"]
        values[f"job:{job_id}"] = job
        jobs_by_hash[hashlib.sha256(job_id.encode()).hexdigest()] = job_id
        keys = [OverlayKey("customer", job["customer"]["id"])]
        location_id = (job.get("address") or {}).get("id")
        if location_id:
            keys.append(OverlayKey("service_location", location_id))
        parents[f"job:{job_id}"] = tuple(keys)
    for path in sorted(schedule.glob("job-*-appointments-http-200.json")):
        job_hash = path.name.split("-")[1]
        job_id = jobs_by_hash.get(job_hash)
        if job_id is None:
            continue
        for appointment in _load(path).get("appointments", []):
            values[f"appointment:{appointment['id']}"] = appointment
            parents[f"appointment:{appointment['id']}"] = (OverlayKey("job", job_id),)
    return values, parents


def build(args: argparse.Namespace) -> CurrentOverlayManifest:
    delta = _load(args.delta)
    successor = _load(args.successor_manifest)
    values, parents = _index(args.refresh, args.schedule)
    held_job_ids = set(args.held_job_ids)
    if args.held_job_detail_root:
        for path in args.held_job_detail_root.glob("open-job-detail-*.json"):
            detail = _load(path)
            if not (detail.get("address") or {}).get("id"):
                held_job_ids.add(detail["id"])
    held_jobs = {
        row["source_id"]
        for row in delta["records"]
        if row["domain"] == "job"
        and row["source_id"] in held_job_ids
    }
    records: list[OverlayRecord] = []
    for row in delta["records"]:
        if row["domain"] not in {"customer", "service_location", "job", "appointment"}:
            continue
        if row["disposition"] in {"UNCHANGED", "OUTSIDE_CURRENT_OPEN_DELTA_SCOPE"}:
            continue
        key = f"{row['domain']}:{row['source_id']}"
        if row["source_id"] in held_jobs:
            assertion = OverlayAssertion.HOLD
        else:
            assertion = {
                "ADDED": OverlayAssertion.CREATE,
                "CHANGED": OverlayAssertion.UPDATE,
                "REMOVED": OverlayAssertion.REMOVE,
            }[row["disposition"]]
        if row["domain"] == "appointment" and any(
            parent.domain == "job" and parent.source_id in held_job_ids
            for parent in parents.get(key, ())
        ):
            assertion = OverlayAssertion.HOLD
        payload = {} if assertion in {OverlayAssertion.HOLD, OverlayAssertion.REMOVE} else values[key]
        records.append(
            OverlayRecord(
                domain=row["domain"],
                source_id=row["source_id"],
                assertion=assertion,
                source_digest=row["after_digest"] or row["before_digest"],
                prior_source_digest=(
                    row["before_digest"] if assertion is OverlayAssertion.UPDATE else None
                ),
                acquired_at=delta["as_of"],
                payload=payload,
                parent_keys=parents.get(key, ()),
                native_fingerprint=(
                    row["after_digest"]
                    if assertion in {OverlayAssertion.CREATE, OverlayAssertion.UPDATE}
                    else None
                ),
                reason=(
                    (
                        "parent_job_missing_location_provider_identity"
                        if row["domain"] == "appointment"
                        else "missing_location_provider_identity"
                    )
                    if assertion is OverlayAssertion.HOLD
                    else ""
                ),
            )
        )
    return CurrentOverlayManifest.build(
        base_source4_digest=args.base_source4_digest,
        delta_digest=delta["digest"],
        company_id=successor["company_id"],
        branch_id=successor["branch_id"],
        acquired_at=delta["as_of"],
        records=tuple(records),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--successor-manifest", type=Path, required=True)
    parser.add_argument("--refresh", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--base-source4-digest", required=True)
    parser.add_argument("--held-job-id", dest="held_job_ids", action="append", default=[])
    parser.add_argument("--held-job-detail-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.private_payload(), indent=2) + "\n")
    os.chmod(args.output, 0o600)
    print(json.dumps({"digest": manifest.digest, "records": len(manifest.records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
