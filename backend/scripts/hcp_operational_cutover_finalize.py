"""Finalize a sealed HCP acquisition into an isolated-clone rehearsal packet.

This command is local-only.  It performs no network or database calls and adds
all source-identifiable notes and complete parent graphs to the classification
and provider-observation packet.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

if __package__:
    from .hcp_operational_cutover_acquisition import (
        _classify,
        _digest,
        _load_object,
        _location_id,
        _parent_id,
        _prior_index,
    )
else:
    from hcp_operational_cutover_acquisition import (
        _classify,
        _digest,
        _load_object,
        _location_id,
        _parent_id,
        _prior_index,
    )


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        value = _load_object(path)
        rows = value.get(key)
        if not isinstance(rows, list):
            raise TypeError(f"{path} does not contain {key} rows")
        result.extend(row for row in rows if isinstance(row, dict))
    return result


def _write_once(root: Path, name: str, value: Any) -> Path:
    target = root / name
    body = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    with target.open("xb") as stream:
        stream.write(body)
    os.chmod(str(target), 0o600)
    return target


def _add(target: dict[tuple[str, str], dict[str, Any]], row: dict[str, Any]) -> None:
    key = (row["domain"], row["source_id"])
    existing = target.get(key)
    if existing is not None and existing != row:
        raise ValueError("conflicting classification for {}:{}".format(*key))
    target[key] = row


def _load_manifest(root: Path) -> dict[str, Any]:
    manifest = _load_object(root / "operational-acquisition-manifest.json")
    expected = manifest.get("digest")
    actual = _digest({key: value for key, value in manifest.items() if key != "digest"})
    if expected != actual:
        raise ValueError("operational acquisition manifest digest mismatch")
    return manifest


def build(args: argparse.Namespace) -> dict[str, Any]:
    source = _load_manifest(args.acquisition_root)
    artifact_addendum: dict[str, Any] | None = None
    if args.artifact_addendum:
        artifact_addendum = _load_object(
            args.artifact_addendum / "open-work-artifact-addendum-manifest.json"
        )
        expected = artifact_addendum.get("digest")
        actual = _digest(
            {key: value for key, value in artifact_addendum.items() if key != "digest"}
        )
        if expected != actual:
            raise ValueError("open-work artifact addendum digest mismatch")
        if artifact_addendum.get("source_manifest_digest") != source.get("digest"):
            raise ValueError("open-work artifact addendum source mismatch")
    attachment_custody: dict[str, Any] | None = None
    if args.attachment_custody:
        attachment_custody = _load_object(
            args.attachment_custody / "attachment-custody-manifest.json"
        )
        expected = attachment_custody.get("digest")
        actual = _digest(
            {key: value for key, value in attachment_custody.items() if key != "digest"}
        )
        if expected != actual:
            raise ValueError("attachment custody digest mismatch")
        if not artifact_addendum or attachment_custody.get(
            "source_artifact_addendum_digest"
        ) != artifact_addendum.get("digest"):
            raise ValueError("attachment custody source mismatch")
    prior_packet = _load_object(args.prior_delta)
    prior = _prior_index(prior_packet)
    customers = _pages(args.acquisition_root, "customers", "customers")
    employees = _pages(args.acquisition_root, "employees", "employees")
    jobs = _pages(args.acquisition_root, "jobs", "jobs")
    estimates = _pages(args.acquisition_root, "estimates", "estimates")
    invoices = _pages(args.acquisition_root, "invoices", "invoices")
    customers_by_id = {row["id"]: row for row in customers}
    jobs_by_id = {row["id"]: row for row in jobs}
    estimates_by_id = {row["id"]: row for row in estimates}
    invoices_by_id = {row["id"]: row for row in invoices}

    original = source.get("classifications")
    if not isinstance(original, list):
        raise TypeError("source manifest classifications are missing")
    scope_job_ids = {
        row["source_id"]
        for row in original
        if isinstance(row, dict) and row.get("domain") == "job"
    }
    scope_estimate_ids = {
        row["source_id"]
        for row in original
        if isinstance(row, dict) and row.get("domain") == "estimate"
    }
    scope_invoice_ids = {
        row["source_id"]
        for row in original
        if isinstance(row, dict) and row.get("domain") == "invoice"
    }
    scope_customer_ids = {
        value
        for value in (
            _parent_id(jobs_by_id[job_id], "customer")
            for job_id in scope_job_ids
            if job_id in jobs_by_id
        )
        if value
    }

    unresolved_location_jobs = {
        row["provider_job_id"]
        for row in source["open_work_reconciliation"]["prior_locationless_jobs"]
        if row.get("result") == "STILL_LOCATION_LESS_OPEN"
    }
    classifications: dict[tuple[str, str], dict[str, Any]] = {}
    payloads: dict[tuple[str, str], dict[str, Any]] = {}
    parents: dict[tuple[str, str], list[dict[str, str]]] = {}

    for customer_id in sorted(scope_customer_ids):
        customer = customers_by_id.get(customer_id)
        if customer is None:
            continue
        key = ("customer", customer_id)
        payloads[key] = customer
        parents[key] = []
        _add(
            classifications,
            _classify(
                domain="customer", source_id=customer_id, payload=customer, prior=prior
            ),
        )
        addresses = customer.get("addresses")
        if isinstance(addresses, list):
            for address in addresses:
                if not isinstance(address, dict) or not isinstance(
                    address.get("id"), str
                ):
                    continue
                key = ("service_location", address["id"])
                payloads[key] = address
                parents[key] = [{"domain": "customer", "source_id": customer_id}]
                _add(
                    classifications,
                    _classify(
                        domain="service_location",
                        source_id=address["id"],
                        payload=address,
                        prior=prior,
                    ),
                )

    for job_id in sorted(scope_job_ids):
        job = jobs_by_id.get(job_id)
        if job is None:
            continue
        job_parents: list[dict[str, str]] = []
        customer_id = _parent_id(job, "customer")
        location_id = _location_id(job)
        if customer_id:
            job_parents.append({"domain": "customer", "source_id": customer_id})
        if location_id:
            job_parents.append({"domain": "service_location", "source_id": location_id})
            address = job.get("address")
            key = ("service_location", location_id)
            if key not in payloads and isinstance(address, dict):
                payloads[key] = address
                parents[key] = (
                    [{"domain": "customer", "source_id": customer_id}]
                    if customer_id
                    else []
                )
                _add(
                    classifications,
                    _classify(
                        domain="service_location",
                        source_id=location_id,
                        payload=address,
                        prior=prior,
                    ),
                )
        key = ("job", job_id)
        payloads[key] = job
        parents[key] = job_parents
        _add(
            classifications,
            _classify(
                domain="job",
                source_id=job_id,
                payload=job,
                prior=prior,
                forced_hold=(
                    "prior location-less open Job remains without provider Location identity"
                    if job_id in unresolved_location_jobs
                    else None
                ),
            ),
        )
        notes = job.get("notes")
        if isinstance(notes, list):
            for note in notes:
                if not isinstance(note, dict) or not isinstance(note.get("id"), str):
                    continue
                _add(
                    classifications,
                    _classify(
                        domain="note",
                        source_id=note["id"],
                        payload=note,
                        prior=prior,
                        forced_hold="source note is evidence-only; author/time provenance is absent where HCP omits it",
                    ),
                )

    prior_provider = _load_object(
        args.acquisition_root / "isolated-clone-provider-observations.json"
    )
    referenced_technician_ids = set()
    referenced_technician_count = 0
    for row in prior_provider.get("records", []):
        if not isinstance(row, dict) or row.get("domain") != "appointment":
            continue
        source_id = row.get("source_id")
        payload = row.get("payload")
        row_parents = row.get("parent_keys")
        if not isinstance(source_id, str) or not isinstance(payload, dict):
            continue
        parent_job = next(
            (
                parent.get("source_id")
                for parent in row_parents or []
                if isinstance(parent, dict) and parent.get("domain") == "job"
            ),
            None,
        )
        forced = (
            "parent Job remains without provider Location identity"
            if parent_job in unresolved_location_jobs
            else None
        )
        key = ("appointment", source_id)
        payloads[key] = payload
        parents[key] = row_parents if isinstance(row_parents, list) else []
        dispatched = payload.get("dispatched_employees_ids")
        if isinstance(dispatched, list):
            referenced_technician_ids.update(
                value for value in dispatched if isinstance(value, str)
            )
            referenced_technician_count += sum(
                1 for value in dispatched if isinstance(value, str)
            )
        _add(
            classifications,
            _classify(
                domain="appointment",
                source_id=source_id,
                payload=payload,
                prior=prior,
                forced_hold=forced,
            ),
        )

    for employee in employees:
        _add(
            classifications,
            _classify(
                domain="employee",
                source_id=employee["id"],
                payload=employee,
                prior=prior,
            ),
        )
    current_employee_ids = {
        employee["id"] for employee in employees if isinstance(employee.get("id"), str)
    }
    missing_technician_ids = referenced_technician_ids - current_employee_ids
    for source_id in sorted(missing_technician_ids):
        payload = {
            "id": source_id,
            "evidence": "current appointment assignment reference",
        }
        _add(
            classifications,
            _classify(
                domain="technician_reference",
                source_id=source_id,
                payload=payload,
                prior=prior,
                forced_hold="appointment technician identity is absent from the current HCP Employee collection",
            ),
        )
    for source_id in sorted(scope_estimate_ids):
        row = estimates_by_id.get(source_id)
        if row is not None:
            _add(
                classifications,
                _classify(
                    domain="estimate", source_id=source_id, payload=row, prior=prior
                ),
            )
    for source_id in sorted(scope_invoice_ids):
        row = invoices_by_id.get(source_id)
        if row is not None:
            _add(
                classifications,
                _classify(
                    domain="invoice", source_id=source_id, payload=row, prior=prior
                ),
            )
    for row in source["open_work_reconciliation"]["legacy_appointment_duplicate_risk"]:
        source_id = row.get("legacy_source_id")
        if isinstance(source_id, str):
            _add(
                classifications,
                {
                    "after_digest": _digest(row),
                    "before_digest": None,
                    "disposition": "HOLD",
                    "domain": "legacy_appointment",
                    "reason": row["reason"],
                    "source_id": source_id,
                },
            )

    if args.artifact_addendum:
        for path in sorted(
            args.artifact_addendum.glob("open-job-expanded-*-http-200.json")
        ):
            detail = _load_object(path)
            for domain, plural in (
                ("note", "notes"),
                ("attachment", "attachments"),
                ("form", "forms"),
            ):
                children = detail.get(plural)
                if not isinstance(children, list):
                    continue
                for child in children:
                    if not isinstance(child, dict) or not isinstance(
                        child.get("id"), str
                    ):
                        continue
                    reason = {
                        "note": "source note is evidence-only; author/time provenance is absent where HCP omits it",
                        "attachment": "source attachment is evidence-only pending content custody and clone reachability",
                        "form": "source form is evidence-only pending clone reachability",
                    }[domain]
                    _add(
                        classifications,
                        _classify(
                            domain=domain,
                            source_id=child["id"],
                            payload=child,
                            prior=prior,
                            forced_hold=reason,
                        ),
                    )

    rows = sorted(
        classifications.values(), key=lambda row: (row["domain"], row["source_id"])
    )
    totals = dict(sorted(Counter(row["disposition"] for row in rows).items()))
    legacy_appointment_holds = sum(
        row["domain"] == "legacy_appointment" and row["disposition"] == "HOLD"
        for row in rows
    )
    domain_totals: dict[str, dict[str, int]] = {}
    for domain in sorted({row["domain"] for row in rows}):
        domain_totals[domain] = dict(
            sorted(
                Counter(
                    row["disposition"] for row in rows if row["domain"] == domain
                ).items()
            )
        )

    observations = {
        "acquired_at": source["acquisition"]["completed_at"],
        "contract": "hcp-operational-rehearsal-provider-observations/v2",
        "records": [
            {
                "acquired_at": source["acquisition"]["completed_at"],
                "domain": domain,
                "parent_keys": parents[(domain, source_id)],
                "payload": payload,
                "source_digest": _digest(payload),
                "source_id": source_id,
                "source_updated_at": payload.get("updated_at"),
            }
            for (domain, source_id), payload in sorted(payloads.items())
        ],
        "source_manifest_digest": source["digest"],
    }
    observations["digest"] = _digest(observations)

    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(str(args.output), 0o700)
    _write_once(args.output, "provider-observations.json", observations)
    final = {
        "acquisition_manifest": "operational-acquisition-manifest.json",
        "acquisition_manifest_digest": source["digest"],
        "artifact_addendum": (
            "open-work-artifact-addendum-manifest.json"
            if args.artifact_addendum
            else None
        ),
        "artifact_addendum_digest": (
            artifact_addendum.get("digest") if artifact_addendum else None
        ),
        "attachment_custody": (
            "attachment-custody-manifest.json" if args.attachment_custody else None
        ),
        "attachment_custody_digest": (
            attachment_custody.get("digest") if attachment_custody else None
        ),
        "classification_by_domain": domain_totals,
        "classification_totals": totals,
        "classifications": rows,
        "contract": "hcp-operational-cutover-gate-packet/v1",
        "provider_observations": "provider-observations.json",
        "provider_observations_digest": observations["digest"],
        "reconciliation": source["open_work_reconciliation"],
        "state": "PREPARED_AWAITING_FRESH_ISOLATED_CLONE_NATIVE_OBSERVATION",
        "unresolved_holds": {
            "appointment_relationship_http_400_jobs": source["coverage"][
                "appointment_http_statuses"
            ].get("400", 0),
            "attachments_evidence_only": sum(
                1 for row in rows if row["domain"] == "attachment"
            ),
            "attachments_content_custody_complete": bool(
                attachment_custody
                and attachment_custody.get("state") == "COMPLETE"
                and attachment_custody.get("count")
                == sum(1 for row in rows if row["domain"] == "attachment")
            ),
            "forms_evidence_only": sum(1 for row in rows if row["domain"] == "form"),
            "forms_source_identity_absent": not any(
                row["domain"] == "form" for row in rows
            ),
            "job_attachment_expansion_http_400": (
                artifact_addendum.get("http_status_counts", {}).get("400", 0)
                if artifact_addendum
                else len(scope_job_ids)
            ),
            "legacy_appointment_duplicate_risk": legacy_appointment_holds,
            "locationless_open_jobs": len(unresolved_location_jobs),
            "note_provenance_partial": sum(
                1 for row in rows if row["domain"] == "note"
            ),
            "technician_assignment_references": referenced_technician_count,
            "technician_identities_absent_from_current_employees": len(
                missing_technician_ids
            ),
        },
    }
    final["digest"] = _digest(final)
    _write_once(args.output, "gate-packet.json", final)
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-root", required=True, type=Path)
    parser.add_argument("--artifact-addendum", type=Path)
    parser.add_argument("--attachment-custody", type=Path)
    parser.add_argument("--prior-delta", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    value = build(args)
    print(
        json.dumps(
            {
                "classification_totals": value["classification_totals"],
                "digest": value["digest"],
                "state": value["state"],
                "unresolved_holds": value["unresolved_holds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
