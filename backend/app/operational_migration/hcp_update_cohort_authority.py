"""Deterministic Migration authority for the accepted SOURCE.4 UPDATE cohort."""

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

CONTRACT: Final = "hcp-update-runtime-cohorts/v1"
AUTHORITY_CONTRACT: Final = "hcp-source4-update-cohort-authority/v1"
GENERATION_VERSION: Final = "migration.hcp.update.cohort.authority.1"
ACCEPTED_SOURCE4_DIGEST: Final = "4a4a9582d7fde37dba73ba9e93db5669d9341768c7f5741f6e8916971fd9ec60"
ACCEPTED_OVERLAY_SHA256: Final = "ce9d4ea1e048a70b7a8a5b85fab33fd1a0568eb5cb1356229187144ab8bc7558"
ACCEPTED_OVERLAY_MANIFEST_DIGEST: Final = "e23b7bcf5ac34ea650184afacc711af0c7028e83a6b1f7405e2ae17e13441eb2"
ACCEPTED_HOLD_SHA256: Final = "c13cb0b565d2b86d34365f12d565f37f0e7ba6ec6bfa0d65de7f4a81ee088324"
EXPECTED_UPDATES: Final = {
    "appointment": 6,
    "customer": 20,
    "job": 254,
    "service_location": 0,
}
EXPECTED_COHORTS: Final = {
    "CURRENT_OPERATIONAL": 8,
    "SAFE_HISTORICAL": 0,
    "SAFE_UPDATE": 37,
    "OTHER_HELD": 235,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def artifact_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "artifact_digest"}
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def _predecessors(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows = json.loads(path.read_bytes())
    if not isinstance(rows, list):
        raise TypeError("accepted predecessor evidence must be a list")
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["entity"]), str(row["native_id"]))
        if key in result:
            raise ValueError(f"duplicate accepted predecessor evidence: {key}")
        result[key] = row
    return result


def build_authority(
    *,
    overlay_path: Path,
    hold_path: Path,
    source_package_manifest_path: Path,
    predecessor_path: Path,
    refresh_root: Path,
    schedule_root: Path,
    cutoff: date = date(2026, 9, 12),
) -> dict[str, Any]:
    """Build the complete cohort solely from accepted immutable evidence."""
    overlay = json.loads(overlay_path.read_bytes())
    source_package = json.loads(source_package_manifest_path.read_bytes())
    if sha256(overlay_path) != ACCEPTED_OVERLAY_SHA256:
        raise ValueError("accepted overlay file digest mismatch")
    if sha256(hold_path) != ACCEPTED_HOLD_SHA256:
        raise ValueError("accepted hold packet digest mismatch")
    if overlay.get("digest") != ACCEPTED_OVERLAY_MANIFEST_DIGEST:
        raise ValueError("accepted overlay manifest digest mismatch")
    if overlay.get("base_source4_digest") != ACCEPTED_SOURCE4_DIGEST:
        raise ValueError("accepted SOURCE.4 package digest mismatch")
    plan = build_acceptance_plan(
        overlay_path=overlay_path,
        refresh_root=refresh_root,
        schedule_root=schedule_root,
        cutoff=cutoff,
    )
    predecessors = _predecessors(predecessor_path)
    overlay_by_key = {
        (str(row["domain"]), str(row["source_id"])): row
        for row in overlay["records"]
    }
    if len(overlay_by_key) != len(overlay["records"]):
        raise ValueError("overlay contains duplicate source assertion identities")

    records: list[dict[str, Any]] = []
    domain_counts: Counter[str] = Counter()
    cohort_counts: Counter[str] = Counter()
    direct_current = 0
    supporting_current = 0
    for accepted in plan.records:
        if accepted.assertion != "update":
            continue
        if (accepted.domain, accepted.source_id) not in overlay_by_key:
            raise ValueError("acceptance plan contains an assertion absent from overlay")
        if accepted.classification in {
            WriteClassification.CURRENT_OPERATIONAL,
            WriteClassification.SAFE_SUPPORTING_PARENT,
        }:
            cohort = "CURRENT_OPERATIONAL"
        elif accepted.classification is WriteClassification.SAFE_UPDATE:
            cohort = "SAFE_UPDATE"
        elif accepted.classification is WriteClassification.SAFE_HISTORICAL:
            cohort = "SAFE_HISTORICAL"
        else:
            cohort = "OTHER_HELD"
        direct = accepted.classification is WriteClassification.CURRENT_OPERATIONAL
        supporting = accepted.classification is WriteClassification.SAFE_SUPPORTING_PARENT
        direct_current += int(direct)
        supporting_current += int(supporting)
        domain_counts[accepted.domain] += 1
        cohort_counts[cohort] += 1
        predecessor = predecessors.get((accepted.domain, accepted.source_id))
        records.append(
            {
                "domain": accepted.domain,
                "source_id": accepted.source_id,
                "original_assertion": "update",
                "assertion_source_digest": accepted.source_digest,
                "cohort": cohort,
                "cohort_evidence": accepted.reason,
                "accepted_predecessor_identity": (
                    accepted.source_id if predecessor is not None else None
                ),
                "accepted_predecessor_evidence_digest": (
                    predecessor.get("source_digest") if predecessor is not None else None
                ),
                "parent_source_identities": list(accepted.parent_keys),
                "company_id": overlay["company_id"],
                "branch_id": overlay["branch_id"],
                "required_by_current_operational_graph": direct,
                "required_as_supporting_parent": supporting,
                "known_current_operational_dependency": direct or supporting,
                "known_financial_truth_dependency": "NOT_ESTABLISHED_BY_THIS_AUTHORITY",
                "accepted_artifact_lineage": {
                    "source_package_digest": overlay["base_source4_digest"],
                    "overlay_manifest_digest": overlay["digest"],
                },
            }
        )

    observed_domains = {domain: domain_counts[domain] for domain in EXPECTED_UPDATES}
    if observed_domains != EXPECTED_UPDATES or len(records) != 280:
        raise ValueError(f"UPDATE cardinality mismatch: {observed_domains}")
    observed_cohorts = {cohort: cohort_counts[cohort] for cohort in EXPECTED_COHORTS}
    if observed_cohorts != EXPECTED_COHORTS:
        raise ValueError(f"cohort accounting mismatch: {observed_cohorts}")
    if direct_current != 3 or supporting_current != 5:
        raise ValueError("current operational UPDATE graph mismatch")
    if source_package.get("package_digest") not in {None, overlay["base_source4_digest"]}:
        raise ValueError("SOURCE.4 package digest mismatch")

    result: dict[str, Any] = {
        "contract": CONTRACT,
        "authority_contract": AUTHORITY_CONTRACT,
        "generation_version": GENERATION_VERSION,
        "mutation_authority": "none",
        "source_package_digest": overlay["base_source4_digest"],
        "source_package_manifest_sha256": sha256(source_package_manifest_path),
        "overlay_file_sha256": sha256(overlay_path),
        "overlay_manifest_digest": overlay["digest"],
        "hold_packet_sha256": sha256(hold_path),
        "accepted_predecessor_packet_sha256": sha256(predecessor_path),
        "company_id": overlay["company_id"],
        "branch_id": overlay["branch_id"],
        "cutoff_date": cutoff.isoformat(),
        "record_count": len(records),
        "counts_by_domain": observed_domains,
        "counts_by_cohort": observed_cohorts,
        "current_operational_update_count": direct_current + supporting_current,
        "direct_current_operational_update_count": direct_current,
        "supporting_parent_update_count": supporting_current,
        "records": sorted(records, key=lambda item: (item["domain"], item["source_id"])),
    }
    result["artifact_digest"] = artifact_digest(result)
    return result


def verify_authority(value: dict[str, Any]) -> None:
    if value.get("contract") != CONTRACT or value.get("authority_contract") != AUTHORITY_CONTRACT:
        raise ValueError("cohort authority contract mismatch")
    if value.get("artifact_digest") != artifact_digest(value):
        raise ValueError("cohort authority digest mismatch")
    if (
        value.get("source_package_digest") != ACCEPTED_SOURCE4_DIGEST
        or value.get("overlay_file_sha256") != ACCEPTED_OVERLAY_SHA256
        or value.get("overlay_manifest_digest") != ACCEPTED_OVERLAY_MANIFEST_DIGEST
        or value.get("hold_packet_sha256") != ACCEPTED_HOLD_SHA256
    ):
        raise ValueError("cohort authority accepted artifact binding mismatch")
    records = value.get("records")
    if not isinstance(records, list) or len(records) != 280:
        raise ValueError("cohort authority must contain exactly 280 records")
    keys = {(row["domain"], row["source_id"]) for row in records}
    if len(keys) != 280 or any(row.get("original_assertion") != "update" for row in records):
        raise ValueError("cohort authority UPDATE identity accounting mismatch")
    if any("native_id" in row or "native_uuid" in row for row in records):
        raise ValueError("cohort authority must not infer ACP native identity")
    domains = Counter(row["domain"] for row in records)
    cohorts = Counter(row["cohort"] for row in records)
    if {domain: domains[domain] for domain in EXPECTED_UPDATES} != EXPECTED_UPDATES:
        raise ValueError("cohort authority domain accounting mismatch")
    if {cohort: cohorts[cohort] for cohort in EXPECTED_COHORTS} != EXPECTED_COHORTS:
        raise ValueError("cohort authority cohort accounting mismatch")
    if records != sorted(records, key=lambda item: (item["domain"], item["source_id"])):
        raise ValueError("cohort authority ordering is not canonical")
