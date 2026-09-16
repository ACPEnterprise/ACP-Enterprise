"""Build a deterministic, non-mutating SOURCE.4 Estimate readiness packet."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-source4-estimate-history-readiness/v1"
GENERATION_VERSION: Final = "migration.historical.operational.admission.1"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Mapping[str, object]) -> str:
    body = {key: item for key, item in value.items() if key != "digest"}
    return hashlib.sha256(canonical_bytes(body)).hexdigest()


def _page_rows(root: Path, *, stem: str, key: str) -> list[dict[str, Any]]:
    paths = sorted(root.glob(f"{stem}/page-*.json"))
    if not paths:
        paths = sorted(root.glob(f"{stem}-page-*.json"))
    if not paths:
        raise ValueError(f"no {stem} source pages found under {root}")
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_bytes())
        page = payload.get(key)
        if not isinstance(page, list):
            raise TypeError(f"{path} does not contain a {key} list")
        rows.extend(page)
    return rows


def _unique(
    rows: Iterable[Mapping[str, Any]], *, label: str, id_field: str = "id"
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        source_id = row.get(id_field)
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(f"{label} source identity is missing")
        if source_id in result:
            raise ValueError(f"duplicate {label} source identity: {source_id}")
        result[source_id] = row
    return result


def build_estimate_history_readiness(
    *,
    source_root: Path,
    acquisition_manifest_path: Path,
    control_crosswalk_path: Path,
    refresh_root: Path | None = None,
    refresh_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Classify sealed Estimates without guessing native or Job identities."""

    estimates = _unique(
        _page_rows(source_root, stem="estimates", key="estimates"), label="Estimate"
    )
    jobs = _unique(_page_rows(source_root, stem="jobs", key="jobs"), label="Job")
    crosswalk = json.loads(control_crosswalk_path.read_bytes())
    if not isinstance(crosswalk, list):
        raise TypeError("Estimate control crosswalk must be a list")
    control_by_id = _unique(
        crosswalk, label="Estimate control", id_field="native_estimate_id"
    )
    if set(control_by_id) != set(estimates):
        raise ValueError("Estimate control crosswalk does not cover sealed Estimates")

    option_to_estimate: dict[str, str] = {}
    for estimate_id, estimate in estimates.items():
        options = estimate.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError(f"Estimate has no source options: {estimate_id}")
        for option in options:
            option_id = option.get("id") if isinstance(option, Mapping) else None
            if not isinstance(option_id, str) or not option_id:
                raise ValueError(f"Estimate option identity is missing: {estimate_id}")
            if option_id in option_to_estimate:
                raise ValueError(f"duplicate Estimate option identity: {option_id}")
            option_to_estimate[option_id] = estimate_id

    job_edges: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for job_id, job in jobs.items():
        raw_ids = job.get("original_estimate_uuids") or []
        if not isinstance(raw_ids, list):
            raise TypeError(f"Job original_estimate_uuids is not a list: {job_id}")
        if not raw_ids and job.get("original_estimate_id"):
            raw_ids = [job["original_estimate_id"]]
        for option_id in raw_ids:
            resolved_estimate_id = option_to_estimate.get(option_id)
            if resolved_estimate_id is None:
                raise ValueError(
                    f"Job references an Estimate option outside sealed authority: {job_id}"
                )
            estimate = estimates[resolved_estimate_id]
            source_customer = (estimate.get("customer") or {}).get("id")
            job_customer = (job.get("customer") or {}).get("id")
            if not source_customer or source_customer != job_customer:
                raise ValueError(
                    "Estimate/Job Customer graph conflicts: "
                    f"{resolved_estimate_id}/{job_id}"
                )
            job_edges[resolved_estimate_id].append(
                {
                    "job_source_id": job_id,
                    "option_source_id": option_id,
                    "job_location_source_id": (job.get("address") or {}).get("id"),
                }
            )

    records: list[dict[str, Any]] = []
    for estimate_id in sorted(estimates):
        estimate = estimates[estimate_id]
        edges = sorted(
            job_edges.get(estimate_id, []),
            key=lambda row: (str(row["job_source_id"]), str(row["option_source_id"])),
        )
        customer_id = (estimate.get("customer") or {}).get("id")
        if not isinstance(customer_id, str) or not customer_id:
            raise ValueError(f"Estimate Customer identity is missing: {estimate_id}")
        location_id = (estimate.get("address") or {}).get("id")
        if len(edges) == 1:
            relationship = "SINGLE_AUTHORITATIVE_JOB"
            disposition = "SAFE_ADMIT_BINDING_DEPENDENT"
            reason = "exact_job_original_estimate_option_relationship"
        elif len(edges) > 1:
            relationship = "MULTIPLE_AUTHORITATIVE_JOBS"
            disposition = "OWNER_DECISION_REQUIRED"
            reason = "native_estimate_contract_requires_one_job_but_source_has_multiple"
        else:
            relationship = "CUSTOMER_ONLY"
            disposition = "CUSTOMER_ONLY_HISTORY"
            reason = "no_authoritative_source_job_relationship"
        control = control_by_id[estimate_id]
        records.append(
            {
                "source_estimate_id": estimate_id,
                "source_customer_id": customer_id,
                "source_location_id": location_id,
                "source_status": estimate.get("work_status"),
                "source_digest": control.get("source_digest"),
                "history_layer": control.get("history_layer"),
                "control_classification": control.get("control_classification"),
                "relationship_classification": relationship,
                "candidate_disposition": disposition,
                "reason": reason,
                "job_relationships": edges,
                "native_binding_requirement": {
                    "customer": True,
                    "location": bool(location_id),
                    "job": len(edges) == 1,
                    "post_admission_snapshot_required": True,
                },
            }
        )

    dispositions = Counter(row["candidate_disposition"] for row in records)
    relationships = Counter(row["relationship_classification"] for row in records)
    if dispositions != Counter(
        {
            "SAFE_ADMIT_BINDING_DEPENDENT": 331,
            "OWNER_DECISION_REQUIRED": 56,
            "CUSTOMER_ONLY_HISTORY": 920,
        }
    ):
        raise ValueError("sealed Estimate relationship accounting changed")

    refresh: dict[str, Any] | None = None
    if refresh_root is not None:
        refreshed = _unique(
            _page_rows(refresh_root, stem="estimates", key="estimates"),
            label="refreshed Estimate",
        )
        removed = sorted(set(estimates) - set(refreshed))
        additions = sorted(set(refreshed) - set(estimates))
        if removed:
            raise ValueError("refresh omits sealed Estimate identities")
        refresh = {
            "classification": "OUTSIDE_SEALED_AUTHORITY",
            "source_count": len(refreshed),
            "sealed_overlap_count": len(estimates),
            "added_count": len(additions),
            "added_source_ids": additions,
            "manifest_sha256": sha256(refresh_manifest_path)
            if refresh_manifest_path is not None
            else None,
        }

    packet: dict[str, Any] = {
        "contract": CONTRACT,
        "generation_version": GENERATION_VERSION,
        "source_authority": {
            "acquisition_manifest_sha256": sha256(acquisition_manifest_path),
            "control_crosswalk_sha256": sha256(control_crosswalk_path),
        },
        "counts": {
            "sealed_estimates": len(records),
            "source_customer_identity_present": sum(
                bool(row["source_customer_id"]) for row in records
            ),
            "source_location_identity_present": sum(
                bool(row["source_location_id"]) for row in records
            ),
            "relationship_classifications": dict(sorted(relationships.items())),
            "candidate_dispositions": dict(sorted(dispositions.items())),
            "native_safe_admit_proven": 0,
        },
        "refresh_delta": refresh,
        "records": records,
        "guardrails": {
            "fuzzy_matching_used": False,
            "native_identity_inferred": False,
            "job_relationship_inferred": False,
            "mutation_authorized": False,
            "safe_admit_requires_post_admission_native_bindings": True,
        },
    }
    packet["digest"] = _digest(packet)
    return packet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--control-crosswalk", type=Path, required=True)
    parser.add_argument("--refresh-root", type=Path)
    parser.add_argument("--refresh-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = build_estimate_history_readiness(
        source_root=args.source_root,
        acquisition_manifest_path=args.acquisition_manifest,
        control_crosswalk_path=args.control_crosswalk,
        refresh_root=args.refresh_root,
        refresh_manifest_path=args.refresh_manifest,
    )
    args.output.write_bytes(canonical_bytes(packet))


if __name__ == "__main__":
    main()
