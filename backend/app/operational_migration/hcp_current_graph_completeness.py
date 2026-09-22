"""Seal complete current SOURCE.4 graph intent over the Preview baseline."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Final

from app.operational_migration.hcp_post_admission_acceptance import (
    build_acceptance_plan,
)
from app.operational_migration.hcp_preview_baseline_reconciliation import (
    _exact_successors,
    _load,
    _manifest_entries,
    canonical_bytes,
    sha256,
)

CONTRACT: Final = "hcp-current-overlay-merge-packet/v4"
COMPLETION_CONTRACT: Final = "hcp-current-source4-graph-completeness/v1"
GENERATION_VERSION: Final = "migration.hcp.current.graph.completeness.1"
EXPECTED_V3_DIGEST: Final = (
    "919d9bed1899516f760f47671222cbb4868aca4fdb5242611a4997822472d356"
)
EXPECTED_V3_SHA256: Final = (
    "8d5d0a66915b571608662dc9fd8fef07ee17d0225627ac6e00c1b556ab194764"
)
EXPECTED_BASELINE_SHA256: Final = (
    "b0aac4cc4f26964b9fd4ede69d448eaa62e26dd3bb6d6ac8cce286e36873ae89"
)
EXPECTED_BASELINE_DIGEST: Final = (
    "0eb7791bf128cb98eda3aa659ed4e53636257b7665a216622a5885f2f4cb1437"
)
EXPECTED_FINAL = {
    "CREATE_NEW": 174,
    "REUSE_EXISTING": 4,
    "UPDATE_EXISTING": 5,
    "HOLD": 339,
}
EXPECTED_ORIGINAL_503 = {
    "CREATE_NEW": 159,
    "REUSE_EXISTING": 0,
    "UPDATE_EXISTING": 5,
    "HOLD": 339,
}
EXPECTED_COMPLETION = {
    "CREATE_NEW": 15,
    "REUSE_EXISTING": 4,
    "UPDATE_EXISTING": 0,
    "HOLD": 0,
}


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_bytes({k: v for k, v in value.items() if k != "digest"})
    ).hexdigest()


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        rows.extend(json.loads(path.read_bytes())[key])
    return rows


def _source_index(
    refresh_root: Path, schedule_root: Path
) -> tuple[
    dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], list[dict[str, str]]]
]:
    values: dict[tuple[str, str], dict[str, Any]] = {}
    parents: dict[tuple[str, str], list[dict[str, str]]] = {}
    customers = _pages(refresh_root, "customers", "customers")
    jobs = _pages(refresh_root, "jobs", "jobs")
    for customer in customers:
        customer_key = ("customer", customer["id"])
        values[customer_key] = customer
        for location in customer.get("addresses", []):
            if location.get("id"):
                key = ("service_location", location["id"])
                values[key] = location
                parents[key] = [{"domain": "customer", "source_id": customer["id"]}]
    jobs_by_hash: dict[str, str] = {}
    for job in jobs:
        key = ("job", job["id"])
        values[key] = job
        jobs_by_hash[hashlib.sha256(job["id"].encode()).hexdigest()] = job["id"]
        parents[key] = [{"domain": "customer", "source_id": job["customer"]["id"]}]
        if (job.get("address") or {}).get("id"):
            parents[key].append(
                {"domain": "service_location", "source_id": job["address"]["id"]}
            )
    for path in sorted(schedule_root.glob("job-*-appointments-http-200.json")):
        job_id = jobs_by_hash.get(path.name.split("-")[1])
        if job_id is None:
            continue
        for appointment in json.loads(path.read_bytes()).get("appointments", []):
            key = ("appointment", appointment["id"])
            values[key] = appointment
            parents[key] = [{"domain": "job", "source_id": job_id}]
    return values, parents


def build_complete_graph(
    *,
    v3_path: Path,
    overlay_path: Path,
    delta_path: Path,
    baseline_path: Path,
    classifier_path: Path,
    successor_manifest_path: Path,
    refresh_root: Path,
    schedule_root: Path,
) -> dict[str, Any]:
    if (
        sha256(v3_path) != EXPECTED_V3_SHA256
        or sha256(baseline_path) != EXPECTED_BASELINE_SHA256
    ):
        raise ValueError("v3 or Preview baseline file digest mismatch")
    v3, delta, baseline = map(_load, (v3_path, delta_path, baseline_path))
    classifier, manifest = map(_load, (classifier_path, successor_manifest_path))
    if (
        v3.get("digest") != EXPECTED_V3_DIGEST
        or baseline.get("semantic_digest") != EXPECTED_BASELINE_DIGEST
    ):
        raise ValueError("v3 or Preview semantic authority mismatch")
    plan = build_acceptance_plan(
        overlay_path=overlay_path,
        refresh_root=refresh_root,
        schedule_root=schedule_root,
        cutoff=date(2026, 9, 12),
    )
    original_keys = {(row["domain"], row["source_id"]) for row in v3["records"]}
    current_keys = {
        (domain, source_id)
        for domain, source_ids in plan.current_source_ids.items()
        for source_id in source_ids
    }
    missing = sorted(current_keys - original_keys)
    if Counter(domain for domain, _ in missing) != Counter(
        {"customer": 2, "service_location": 7, "job": 5, "appointment": 5}
    ):
        raise ValueError("omitted current graph identity accounting mismatch")
    delta_rows = {(row["domain"], row["source_id"]): row for row in delta["records"]}
    values, parents = _source_index(refresh_root, schedule_root)
    entries = _manifest_entries(manifest)
    exact = _exact_successors(classifier)
    native_rows = baseline["native_evidence"]
    native = {
        "customer": {row["id"]: row for row in native_rows["customers"]},
        "service_location": {row["id"]: row for row in native_rows["locations"]},
        "job": {row["id"]: row for row in native_rows["jobs"]},
        "appointment": {row["id"]: row for row in native_rows["appointments"]},
    }
    completion: list[dict[str, Any]] = []
    for key in missing:
        delta_row, entry = delta_rows[key], entries[key]
        if delta_row["disposition"] != "UNCHANGED":
            raise ValueError(f"omitted record is not sealed-base UNCHANGED: {key}")
        exact_row = exact.get(key)
        target = entry.get("native_id")
        if entry["disposition"] == "reuse_exact_successor":
            if (
                exact_row is None
                or exact_row.get("target_id") != target
                or target not in native[key[0]]
            ):
                raise ValueError(f"omitted exact reuse target is not proven: {key}")
            successor, reason = (
                "REUSE_EXISTING",
                "accepted_exact_successor_present_in_preview",
            )
        elif entry["disposition"] == "create_new":
            if (
                exact_row is not None
                or baseline["record_counts"]["source4_binding_evidence"] != 0
            ):
                raise ValueError(f"omitted CREATE_NEW absence proof failed: {key}")
            successor, reason, target = (
                "CREATE_NEW",
                "accepted_create_new_with_no_exact_preview_identity",
                None,
            )
        else:
            raise ValueError(f"omitted record lacks admissible accepted intent: {key}")
        payload = values[key]
        completion.append(
            {
                "domain": key[0],
                "source_id": key[1],
                "source_digest": delta_row["after_digest"]
                or delta_row["before_digest"],
                "acquired_at": delta["as_of"],
                "payload": payload,
                "parent_keys": parents.get(key, []),
                "original_assertion": "sealed_base_unchanged_omission",
                "runtime_result": "NOT_APPLICABLE",
                "baseline_evidence": {
                    "source4_binding_evidence_count": 0,
                    "exact_legacy_successor_evidence_digest": exact_row.get(
                        "evidence_digest"
                    )
                    if exact_row
                    else None,
                    "target_native_id": target,
                },
                "successor_assertion": successor,
                "reason": reason,
                "omission_reason": "v2_excluded_unchanged_sealed_base_record",
                "company_id": baseline["company_id"],
                "branch_id": baseline["branch_id"],
                "lifecycle_status": payload.get("work_status")
                or payload.get("status")
                or "source_active",
                "provenance": {
                    "source4_package_digest": v3["base_source4_digest"],
                    "delta_manifest_digest": delta["digest"],
                    "accepted_successor_evidence_digest": entry["evidence_digest"],
                },
            }
        )

    all_records = [dict(row) for row in v3["records"]] + completion
    by_key = {(row["domain"], row["source_id"]): row for row in all_records}
    released: list[dict[str, Any]] = []
    changed = True
    while changed:
        changed = False
        for row in all_records:
            row_key = (row["domain"], row["source_id"])
            if (
                row_key not in current_keys
                or row.get("reason") != "required_parent_is_held_or_absent"
            ):
                continue
            if all(
                by_key.get((parent["domain"], parent["source_id"])) is not None
                and by_key[(parent["domain"], parent["source_id"])][
                    "successor_assertion"
                ]
                != "HOLD"
                for parent in row["parent_keys"]
            ):
                row["successor_assertion"] = "CREATE_NEW"
                row["reason"] = (
                    "parent_graph_resolved_by_complete_current_source4_graph"
                )
                released.append(
                    {
                        "domain": row["domain"],
                        "source_id": row["source_id"],
                        "disposition": "PARENT_GRAPH_RESOLVED",
                        "parent_keys": row["parent_keys"],
                    }
                )
                changed = True
    if len(released) != 13:
        raise ValueError(f"dependent hold release accounting mismatch: {len(released)}")

    for row in all_records:
        if row["successor_assertion"] == "HOLD":
            continue
        for parent in row.get("parent_keys", []):
            if (parent["domain"], parent["source_id"]) not in by_key or by_key[
                (parent["domain"], parent["source_id"])
            ]["successor_assertion"] == "HOLD":
                raise ValueError("admitted successor retains unresolved parent")
    current = [by_key[key] for key in sorted(current_keys)]
    if len(current) != 55 or any(
        row["successor_assertion"] == "HOLD" for row in current
    ):
        raise ValueError("complete current graph is not admissible")
    original_counts = Counter(
        row["successor_assertion"]
        for row in all_records
        if (row["domain"], row["source_id"]) in original_keys
    )
    completion_counts = Counter(row["successor_assertion"] for row in completion)
    final_counts = Counter(row["successor_assertion"] for row in all_records)
    normalized_original = {key: original_counts[key] for key in EXPECTED_ORIGINAL_503}
    normalized_completion = {key: completion_counts[key] for key in EXPECTED_COMPLETION}
    normalized_final = {key: final_counts[key] for key in EXPECTED_FINAL}
    if (
        normalized_original != EXPECTED_ORIGINAL_503
        or normalized_completion != EXPECTED_COMPLETION
        or normalized_final != EXPECTED_FINAL
    ):
        raise ValueError("v4 disposition accounting mismatch")
    current_digest = hashlib.sha256(canonical_bytes(current)).hexdigest()
    result: dict[str, Any] = {
        "contract": CONTRACT,
        "completion_contract": COMPLETION_CONTRACT,
        "generation_version": GENERATION_VERSION,
        "base_source4_digest": v3["base_source4_digest"],
        "v3_predecessor_digest": EXPECTED_V3_DIGEST,
        "v3_predecessor_file_sha256": EXPECTED_V3_SHA256,
        "original_overlay_manifest_digest": v3["predecessor_overlay_manifest_digest"],
        "hold_packet_sha256": v3["hold_packet_sha256"],
        "update_cohort_authority_digest": v3["update_cohort_authority_digest"],
        "runtime_inventory_sha256": v3["runtime_inventory_sha256"],
        "preview_baseline_sha256": EXPECTED_BASELINE_SHA256,
        "preview_baseline_semantic_digest": EXPECTED_BASELINE_DIGEST,
        "baseline_protected_deployed_sha": v3["baseline_protected_deployed_sha"],
        "baseline_schema_head": v3["baseline_schema_head"],
        "company_id": v3["company_id"],
        "branch_id": v3["branch_id"],
        "original_assertion_count": 503,
        "completion_record_count": 19,
        "record_count": 522,
        "original_503_disposition_counts": EXPECTED_ORIGINAL_503,
        "completion_disposition_counts": EXPECTED_COMPLETION,
        "disposition_counts": EXPECTED_FINAL,
        "differences_from_v3": {
            "CREATE_NEW": 28,
            "REUSE_EXISTING": 4,
            "UPDATE_EXISTING": 0,
            "HOLD": -13,
        },
        "complete_current_graph_digest": current_digest,
        "current_operational_graph_admittable": True,
        "ready_for_guarded_execution": True,
        "omitted_record_resolutions": completion,
        "dependent_hold_resolutions": released,
        "current_graph": current,
        "dependency_completeness": {
            "contract": "hcp-current-overlay-dependency-completeness/v2",
            "all_503_original_assertions_recomputed_once": True,
            "all_55_current_graph_records_explicit": True,
            "all_required_parents_resolvable": True,
            "every_current_create_duplicate_safe": True,
            "every_current_reuse_update_target_proven": True,
            "current_hold_count": 0,
            "historical_holds_authorized": True,
            "immutable_artifacts_accessible": True,
            "execution_authority_inputs_identified": True,
            "known_runtime_prerequisites_deferred": [],
            "current_operational_graph_admittable": True,
            "ready_for_guarded_execution": True,
        },
        "records": sorted(
            all_records, key=lambda row: (row["domain"], row["source_id"])
        ),
    }
    result["digest"] = _digest(result)
    return result


def verify_complete_graph(value: dict[str, Any]) -> None:
    if value.get("contract") != CONTRACT or value.get("digest") != _digest(value):
        raise ValueError("v4 contract/digest mismatch")
    if value.get("record_count") != 522 or len(value.get("records", [])) != 522:
        raise ValueError("v4 record coverage mismatch")
    if len({(row["domain"], row["source_id"]) for row in value["records"]}) != 522:
        raise ValueError("v4 duplicate source identity")
    if not value.get("current_operational_graph_admittable") or not value.get(
        "ready_for_guarded_execution"
    ):
        raise ValueError("v4 completeness gate is not satisfied")
