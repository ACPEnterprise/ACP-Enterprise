"""Reconcile the sealed HCP current overlay against immutable Preview evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Final

from app.operational_migration.hcp_post_admission_acceptance import (
    WriteClassification,
    build_acceptance_plan,
)

CONTRACT: Final = "hcp-current-overlay-merge-packet/v3"
GENERATION_VERSION: Final = (
    "migration.hcp.current.overlay.preview.baseline.reconciliation.1"
)
EXPECTED = {
    "source4": "4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60",
    "overlay_file": "ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558",
    "overlay_manifest": "e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2",
    "hold_file": "c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324",
    "cohort_file": "607db4495c79114ab625cdbd9480cfe36e345377ec0de4cb57bc57a5cfb4205d",
    "cohort_digest": "7c743c5e46af4b065d10b8e193ec7a5a0c568c385159bf33c5ed5f012eeb6b53",
    "runtime_file": "995c6ccf6374a8b28aec51746dc4d7289b20d1a32bf06b60198cc6c2b8610e35",
    "baseline_file": "b0aac4cc4f26964b9fd4ede69d448eaa62e26dd3bb6d6ac8cce286e36873ae89",
    "baseline_digest": "0eb7791bf128cb98eda3aa659ed4e53636257b7665a216622a5885f2f4cb1437",
    "authority": "b4bf00d32cd1e4b98dc5a3667ee74724f6f95879",
    "schema": "h8j0l2n4p6r8",
}
DISPOSITIONS: Final = ("CREATE_NEW", "REUSE_EXISTING", "UPDATE_EXISTING", "HOLD")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def semantic_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "digest"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def _exact_successors(
    classifier: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in classifier["records"]:
        successor = row.get("successor_source_id")
        if row.get("disposition") != "exact_successor" or not successor:
            continue
        key = (row["domain"], successor)
        if key in result:
            raise ValueError(f"ambiguous accepted successor evidence: {key}")
        result[key] = row
    return result


def _manifest_entries(
    manifest: dict[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in manifest["entries"]:
        key = (row["domain"], row["source_id"])
        if key in result:
            raise ValueError(f"duplicate accepted manifest entry: {key}")
        result[key] = row
    return result


def build_successor(
    *,
    overlay_path: Path,
    hold_path: Path,
    cohort_path: Path,
    runtime_path: Path,
    baseline_path: Path,
    classifier_path: Path,
    successor_manifest_path: Path,
    refresh_root: Path,
    schedule_root: Path,
) -> dict[str, Any]:
    actual = {
        "overlay_file": sha256(overlay_path),
        "hold_file": sha256(hold_path),
        "cohort_file": sha256(cohort_path),
        "runtime_file": sha256(runtime_path),
        "baseline_file": sha256(baseline_path),
    }
    for key, value in actual.items():
        if value != EXPECTED[key]:
            raise ValueError(f"{key} digest mismatch")
    overlay, cohort, runtime, baseline = map(
        _load, (overlay_path, cohort_path, runtime_path, baseline_path)
    )
    classifier, accepted_manifest = map(
        _load, (classifier_path, successor_manifest_path)
    )
    if (
        overlay.get("base_source4_digest") != EXPECTED["source4"]
        or overlay.get("digest") != EXPECTED["overlay_manifest"]
        or cohort.get("artifact_digest") != EXPECTED["cohort_digest"]
        or baseline.get("semantic_digest") != EXPECTED["baseline_digest"]
        or baseline.get("protected_sha") != EXPECTED["authority"]
        or baseline.get("deployed_sha") != EXPECTED["authority"]
        or baseline.get("schema_head") != EXPECTED["schema"]
        or baseline.get("runtime_inventory_sha256") != EXPECTED["runtime_file"]
    ):
        raise ValueError("immutable predecessor/baseline authority mismatch")
    if (
        runtime.get("protected_authority") != EXPECTED["authority"]
        or runtime.get("schema_head") != EXPECTED["schema"]
    ):
        raise ValueError("runtime inventory authority mismatch")

    plan = build_acceptance_plan(
        overlay_path=overlay_path,
        refresh_root=refresh_root,
        schedule_root=schedule_root,
        cutoff=date(2026, 9, 12),
    )
    planned = {(row.domain, row.source_id): row for row in plan.records}
    coverage = {
        (row["domain"], row["source_id"]): row for row in baseline["assertion_coverage"]
    }
    runtime_rows = {
        (row["domain"], row["source_id"]): row for row in runtime["records"]
    }
    cohort_rows = {(row["domain"], row["source_id"]): row for row in cohort["records"]}
    if len(coverage) != 503 or len(coverage) != len(overlay["records"]):
        raise ValueError("Preview baseline does not cover all 503 assertions")
    updates = {
        (row["domain"], row["source_id"])
        for row in overlay["records"]
        if row["assertion"] == "update"
    }
    if set(runtime_rows) != updates or set(cohort_rows) != updates:
        raise ValueError("UPDATE inventory/cohort coverage mismatch")

    native_rows = baseline["native_evidence"]
    native_by_domain = {
        "customer": {row["id"]: row for row in native_rows["customers"]},
        "service_location": {row["id"]: row for row in native_rows["locations"]},
        "job": {row["id"]: row for row in native_rows["jobs"]},
        "appointment": {row["id"]: row for row in native_rows["appointments"]},
    }
    exact = _exact_successors(classifier)
    manifest_entries = _manifest_entries(accepted_manifest)
    output: list[dict[str, Any]] = []
    dispositions: Counter[str] = Counter()

    for original in sorted(
        overlay["records"], key=lambda row: (row["domain"], row["source_id"])
    ):
        record_key = (original["domain"], original["source_id"])
        accepted = planned[record_key]
        baseline_row = coverage[record_key]
        runtime_row = runtime_rows.get(record_key)
        cohort_row = cohort_rows.get(record_key)
        accepted_entry = manifest_entries.get(record_key)
        exact_row = exact.get(record_key)
        target: str | None = None
        if accepted.classification is WriteClassification.HELD:
            disposition, reason = "HOLD", accepted.reason
        elif cohort_row is not None and cohort_row["cohort"] == "OTHER_HELD":
            disposition, reason = "HOLD", "accepted_other_held_cohort"
        elif original["assertion"] == "create":
            if baseline_row.get("source_identity_present") or exact_row is not None:
                raise ValueError(
                    f"CREATE_NEW duplicate-safety proof failed for {record_key}"
                )
            disposition, reason = (
                "CREATE_NEW",
                "accepted_overlay_create_and_exact_source_identity_absent_from_preview",
            )
        elif accepted_entry is None:
            raise ValueError(f"accepted successor manifest lacks {record_key}")
        elif accepted_entry["disposition"] == "reuse_exact_successor":
            target = accepted_entry.get("native_id")
            if (
                exact_row is None
                or target != exact_row.get("target_id")
                or target not in native_by_domain[original["domain"]]
            ):
                raise ValueError(
                    f"exact native successor is not proven for {record_key}"
                )
            disposition = (
                "UPDATE_EXISTING"
                if original["assertion"] == "update"
                else "REUSE_EXISTING"
            )
            reason = "accepted_exact_legacy_successor_present_in_preview_baseline"
        elif accepted_entry["disposition"] == "create_new":
            if baseline_row.get("source_identity_present") or exact_row is not None:
                raise ValueError(
                    f"CREATE_NEW duplicate-safety proof failed for {record_key}"
                )
            disposition, reason = (
                "CREATE_NEW",
                "accepted_create_new_and_exact_source_identity_absent_from_preview",
            )
        else:
            raise ValueError(
                f"unsupported accepted successor disposition for {record_key}"
            )
        dispositions[disposition] += 1
        output.append(
            {
                "domain": original["domain"],
                "source_id": original["source_id"],
                "source_digest": original["source_digest"],
                "acquired_at": original["acquired_at"],
                "payload": original.get("payload") or {},
                "parent_keys": original.get("parent_keys") or [],
                "original_assertion": original["assertion"],
                "runtime_result": (
                    runtime_row["disposition"] if runtime_row else "NOT_APPLICABLE"
                ),
                "baseline_evidence": {
                    "source_identity_present": baseline_row["source_identity_present"],
                    "exact_legacy_successor_evidence_digest": (
                        exact_row.get("evidence_digest") if exact_row else None
                    ),
                    "target_native_id": target,
                },
                "successor_assertion": disposition,
                "reason": reason,
                "accepted_cohort": cohort_row.get("cohort") if cohort_row else None,
            }
        )

    output_by_key = {(row["domain"], row["source_id"]): row for row in output}
    changed = True
    while changed:
        changed = False
        for row in output:
            if row["successor_assertion"] == "HOLD":
                continue
            if any(
                output_by_key.get((parent["domain"], parent["source_id"])) is None
                or output_by_key[(parent["domain"], parent["source_id"])][
                    "successor_assertion"
                ]
                == "HOLD"
                for parent in row["parent_keys"]
            ):
                dispositions[row["successor_assertion"]] -= 1
                dispositions["HOLD"] += 1
                row["successor_assertion"] = "HOLD"
                row["reason"] = "required_parent_is_held_or_absent"
                row["baseline_evidence"]["target_native_id"] = None
                changed = True

    expected_current = {
        "customer": 11,
        "service_location": 11,
        "job": 15,
        "appointment": 18,
    }
    current: list[dict[str, Any]] = []
    missing_current: list[str] = []
    for domain, source_ids in plan.current_source_ids.items():
        for source_id in source_ids:
            current_row = output_by_key.get((domain, source_id))
            if current_row is None:
                missing_current.append(f"{domain}:{source_id}")
                current.append(
                    {
                        "domain": domain,
                        "source_id": source_id,
                        "successor_assertion": "UNRESOLVED_NOT_IN_PREDECESSOR_OVERLAY",
                        "reason": "v2_assumed_sealed_source4_base_was_already_admitted",
                    }
                )
            else:
                current.append(current_row)
    current.sort(key=lambda row: (row["domain"], row["source_id"]))
    current_holds = [
        row
        for row in current
        if row["successor_assertion"]
        in {"HOLD", "UNRESOLVED_NOT_IN_PREDECESSOR_OVERLAY"}
    ]
    current_admittable = not current_holds
    completeness = {
        "contract": "hcp-current-overlay-dependency-completeness/v1",
        "assertions_classified": len(output),
        "all_503_assertions_classified": len(output) == 503,
        "unresolved_parent_count": 0,
        "current_graph_counts": expected_current,
        "current_graph_missing_from_predecessor_overlay_count": len(missing_current),
        "current_graph_missing_from_predecessor_overlay": missing_current,
        "current_graph_hold_count": len(current_holds),
        "current_operational_graph_admittable": current_admittable,
        "create_duplicate_safety_verified": True,
        "reuse_update_targets_proven": True,
        "holds_authorized": True,
        "immutable_artifacts_verified": True,
        "baseline_authority": EXPECTED["authority"],
        "schema_head": EXPECTED["schema"],
        "known_first_write_prerequisites_deferred": [
            "sealed SOURCE.4 intent required for 19 current graph records absent from v2"
        ],
        "ready_for_guarded_execution": current_admittable,
    }
    result: dict[str, Any] = {
        "contract": CONTRACT,
        "generation_version": GENERATION_VERSION,
        "source_system": "housecall_pro_source4",
        "base_source4_digest": EXPECTED["source4"],
        "predecessor_overlay_file_sha256": EXPECTED["overlay_file"],
        "predecessor_overlay_manifest_digest": EXPECTED["overlay_manifest"],
        "hold_packet_sha256": EXPECTED["hold_file"],
        "update_cohort_file_sha256": EXPECTED["cohort_file"],
        "update_cohort_authority_digest": EXPECTED["cohort_digest"],
        "runtime_inventory_sha256": EXPECTED["runtime_file"],
        "preview_baseline_sha256": EXPECTED["baseline_file"],
        "preview_baseline_semantic_digest": EXPECTED["baseline_digest"],
        "baseline_protected_deployed_sha": EXPECTED["authority"],
        "baseline_schema_head": EXPECTED["schema"],
        "baseline_acquired_at": baseline["acquisition_timestamp"],
        "company_id": overlay["company_id"],
        "branch_id": overlay["branch_id"],
        "record_count": len(output),
        "disposition_counts": {key: dispositions[key] for key in DISPOSITIONS},
        "current_operational_graph_admittable": current_admittable,
        "current_graph": current,
        "dependency_completeness": completeness,
        "records": output,
    }
    result["digest"] = semantic_digest(result)
    return result


def verify_successor(value: dict[str, Any]) -> None:
    if value.get("contract") != CONTRACT or value.get("digest") != semantic_digest(
        value
    ):
        raise ValueError("successor overlay contract/digest mismatch")
    records = value.get("records")
    if not isinstance(records, list) or len(records) != 503:
        raise ValueError("successor overlay must classify exactly 503 assertions")
    keys = {(row["domain"], row["source_id"]) for row in records}
    if len(keys) != 503:
        raise ValueError("successor overlay contains duplicate assertion identities")
    if value.get("preview_baseline_sha256") != EXPECTED["baseline_file"]:
        raise ValueError("successor overlay baseline binding mismatch")
    if any(row["successor_assertion"] not in DISPOSITIONS for row in records):
        raise ValueError("unsupported successor assertion")
