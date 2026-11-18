"""Offline validation for the sealed HCP operational cutover gate.

The validator has no network or database dependency.  It verifies create-once
evidence, source lineage, raw response seals, attachment custody, deterministic
classification accounting, and technician-reference dispositions.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_GATE_COUNTS = {
    "open_jobs": 404,
    "appointments": 547,
    "customers": 633,
    "locations": 966,
    "employees": 5,
    "missing_technicians": 37,
    "locationless_jobs": 22,
    "legacy_appointments": 13,
    "holds": 2065,
    "attachments": 621,
}
FINAL_POLICY_CONTRACT = "hcp-final-operational-cutover-disposition/v1"
EXPECTED_OPERATIONAL_POLICY_HOLDS = {
    "explicit": 46,
    "with_parent_cascade": 67,
    "job": 33,
    "appointment": 30,
    "service_location": 4,
}


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain a JSON object")
    return value


def verify_document_digest(value: Mapping[str, Any], label: str) -> str:
    expected = value.get("digest")
    actual = canonical_digest(
        {key: item for key, item in value.items() if key != "digest"}
    )
    if expected != actual:
        raise ValueError(f"{label} digest mismatch")
    return actual


def require_private_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"sealed evidence file is missing: {path}")
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError(f"sealed evidence file must have mode 0600: {path}")


def _artifact_rows(
    manifest: Mapping[str, Any], root: Path, *, content: bool = False
) -> list[dict[str, Any]]:
    key = "attachments" if content else "artifacts"
    raw = manifest.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"sealed manifest is missing {key}")
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("artifact"), str):
            raise TypeError(f"sealed manifest contains an invalid {key} row")
        artifact = item["artifact"]
        if Path(artifact).name != artifact or artifact in identities:
            raise ValueError(
                f"sealed manifest contains an unsafe/duplicate artifact: {artifact}"
            )
        identities.add(artifact)
        path = root / artifact
        require_private_file(path)
        expected_size = item.get("size_bytes")
        expected_digest = item.get("content_sha256" if content else "sha256")
        if path.stat().st_size != expected_size or file_sha256(path) != expected_digest:
            raise ValueError(f"sealed artifact mismatch: {artifact}")
        rows.append(item)
    return rows


def _raw_page_seal(rows: Iterable[Mapping[str, Any]]) -> str:
    return canonical_digest(
        [
            {
                "artifact": row["artifact"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in sorted(rows, key=lambda item: str(item["artifact"]))
        ]
    )


def _raw_content_seal(rows: Iterable[Mapping[str, Any]]) -> str:
    return canonical_digest(
        [
            {
                "artifact": row["artifact"],
                "content_sha256": row["content_sha256"],
                "size_bytes": row["size_bytes"],
                "source_id": row["source_id"],
            }
            for row in sorted(rows, key=lambda item: str(item["source_id"]))
        ]
    )


def _verify_classifications(gate: Mapping[str, Any]) -> tuple[int, dict[str, int]]:
    rows = gate.get("classifications")
    if not isinstance(rows, list):
        raise TypeError("gate classifications are missing")
    keys: set[tuple[str, str]] = set()
    dispositions: Counter[str] = Counter()
    by_domain: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("gate classification row is invalid")
        key = (str(row.get("domain")), str(row.get("source_id")))
        if key in keys or not all(key):
            raise ValueError("gate classification identities are invalid")
        keys.add(key)
        disposition = str(row.get("disposition"))
        if disposition not in {"CREATE", "UPDATE", "REPLAY", "HOLD"}:
            raise ValueError(f"unsupported gate disposition: {disposition}")
        dispositions[disposition] += 1
        by_domain[key[0]][disposition] += 1
    observed = dict(sorted(dispositions.items()))
    observed_domains = {
        domain: dict(sorted(values.items()))
        for domain, values in sorted(by_domain.items())
    }
    if gate.get("classification_totals") != observed:
        raise ValueError("gate classification totals mismatch")
    if gate.get("classification_by_domain") != observed_domains:
        raise ValueError("gate domain classification totals mismatch")
    return len(rows), observed


def validate_final_policy(
    path: Path,
    *,
    gate: Mapping[str, Any],
    gate_digest: str,
) -> tuple[dict[str, Any], str]:
    """Verify the final policy and its exact corrections to the original gate."""

    require_private_file(path)
    policy = load_object(path)
    if policy.get("contract") != FINAL_POLICY_CONTRACT:
        raise ValueError("final operational policy contract mismatch")
    policy_digest = verify_document_digest(policy, "final operational policy")
    if (
        policy.get("source_gate_digest") != gate_digest
        or policy.get("source_mutation") is not False
        or policy.get("live_database_access") is not False
        or policy.get("network_access") is not False
        or policy.get("unexplained_omissions_in_original_gate") != []
    ):
        raise ValueError("final operational policy boundary mismatch")

    classifications = {
        (str(row.get("domain")), str(row.get("source_id"))): str(
            row.get("disposition")
        )
        for row in gate.get("classifications", [])
        if isinstance(row, dict)
    }
    omissions = policy.get("resolved_original_gate_omissions")
    if not isinstance(omissions, list) or len(omissions) != 2:
        raise ValueError("final operational policy omission inventory mismatch")
    expected_omissions = {
        ("job", "HOLD_QUARANTINE"),
        ("appointment", "HOLD"),
    }
    observed_omissions: set[tuple[str, str]] = set()
    for row in omissions:
        if not isinstance(row, dict):
            raise TypeError("final operational policy omission row is invalid")
        domain = str(row.get("domain"))
        source_id = str(row.get("source_id"))
        original = str(row.get("original_disposition"))
        final = str(row.get("final_disposition"))
        if (
            not domain
            or not source_id
            or classifications.get((domain, source_id)) != original
            or original in {"HOLD", "HOLD_QUARANTINE"}
            or row.get("affects_strict_open_work") is not True
            or row.get("blocks_unrelated_clean_current_open_work") is not False
        ):
            raise ValueError("final operational policy omission evidence mismatch")
        observed_omissions.add((domain, final))
    if observed_omissions != expected_omissions:
        raise ValueError("final operational policy omission disposition mismatch")

    held = policy.get("held_quarantined")
    if not isinstance(held, dict):
        raise TypeError("final operational policy hold inventory is missing")
    inventories = {
        "job": ("locationless_open_jobs", 23),
        "appointment": ("appointments_inheriting_locationless_parent_hold", 18),
        "service_location": ("held_service_location_identities", 4),
    }
    for domain, (name, expected) in inventories.items():
        row = held.get(name)
        source_ids = row.get("source_ids") if isinstance(row, dict) else None
        if (
            not isinstance(source_ids, list)
            or len(source_ids) != expected
            or len(set(source_ids)) != expected
            or any(not isinstance(source_id, str) for source_id in source_ids)
        ):
            raise ValueError(f"final operational policy {domain} holds mismatch")
    unassigned = held.get("unassigned_appointment")
    if (
        not isinstance(unassigned, dict)
        or unassigned.get("count") != 1
        or not isinstance(unassigned.get("source_id"), str)
    ):
        raise ValueError("final operational policy unassigned Appointment mismatch")
    return policy, policy_digest


def required_operational_holds(
    *,
    gate: Mapping[str, Any],
    provider: Mapping[str, Any],
    final_policy: Mapping[str, Any],
) -> dict[tuple[str, str], str]:
    """Return exact operational holds, including policy and parent propagation."""

    provider_rows = provider.get("records")
    if not isinstance(provider_rows, list):
        raise TypeError("provider observations are missing records")
    provider_keys = {
        (str(row.get("domain")), str(row.get("source_id")))
        for row in provider_rows
        if isinstance(row, dict)
    }
    holds: dict[tuple[str, str], str] = {
        (str(row.get("domain")), str(row.get("source_id"))): str(
            row.get("reason") or "sealed original-gate hold"
        )
        for row in gate.get("classifications", [])
        if isinstance(row, dict)
        and row.get("disposition") == "HOLD"
        and (str(row.get("domain")), str(row.get("source_id"))) in provider_keys
    }
    for row in final_policy["resolved_original_gate_omissions"]:
        key = (str(row["domain"]), str(row["source_id"]))
        if key not in provider_keys:
            raise ValueError("final-policy omission is outside provider scope")
        holds[key] = "final policy resolves original-gate omission as held"
    unassigned = final_policy["held_quarantined"]["unassigned_appointment"]
    unassigned_key = ("appointment", str(unassigned["source_id"]))
    if unassigned_key not in provider_keys:
        raise ValueError("held unassigned Appointment is outside provider scope")
    holds[unassigned_key] = "final policy requires owner-confirmation hold"
    if len(holds) != EXPECTED_OPERATIONAL_POLICY_HOLDS["explicit"]:
        raise ValueError("explicit operational cutover hold inventory mismatch")
    return holds


def operational_hold_closure(
    provider: Mapping[str, Any],
    explicit_holds: Mapping[tuple[str, str], str],
) -> set[tuple[str, str]]:
    """Expand operational holds across exact provider parent lineage."""

    held = set(explicit_holds)
    rows = provider.get("records")
    if not isinstance(rows, list):
        raise TypeError("provider observations are missing records")
    while True:
        additions: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("provider observation row is invalid")
            key = (str(row.get("domain")), str(row.get("source_id")))
            parents = {
                (str(parent.get("domain")), str(parent.get("source_id")))
                for parent in row.get("parent_keys", [])
                if isinstance(parent, dict)
            }
            if key not in held and parents & held:
                additions.add(key)
        if not additions:
            break
        held.update(additions)
    return held


def _provider_operational_counts(provider: Mapping[str, Any]) -> dict[str, int]:
    rows = provider.get("records")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise TypeError("provider observations are missing records")
    open_statuses = {"scheduled", "needs scheduling", "in progress"}
    open_jobs = {
        str(row["source_id"])
        for row in rows
        if row.get("domain") == "job"
        and isinstance(row.get("payload"), dict)
        and row["payload"].get("work_status") in open_statuses
    }
    all_jobs = {
        str(row["source_id"]) for row in rows if row.get("domain") == "job"
    }
    appointments = 0
    for row in rows:
        if row.get("domain") != "appointment":
            continue
        parents = row.get("parent_keys")
        if not isinstance(parents, list):
            raise TypeError("provider Appointment parent lineage is invalid")
        job_parents = [
            str(parent.get("source_id"))
            for parent in parents
            if isinstance(parent, dict) and parent.get("domain") == "job"
        ]
        if len(job_parents) != 1 or job_parents[0] not in all_jobs:
            raise ValueError("provider Appointment relationship is unresolved")
        if any(
            isinstance(parent, dict)
            and parent.get("domain") == "job"
            and parent.get("source_id") in open_jobs
            for parent in parents
        ):
            appointments += 1
    return {
        "open_jobs": len(open_jobs),
        "appointments": appointments,
        "customers": sum(row.get("domain") == "customer" for row in rows),
        "locations": sum(row.get("domain") == "service_location" for row in rows),
    }


def _pages(root: Path, stem: str, key: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"{stem}-page-*.json")):
        value = load_object(path)
        page = value.get(key)
        if not isinstance(page, list) or not all(
            isinstance(item, dict) for item in page
        ):
            raise ValueError(f"{path.name} does not contain {key}")
        rows.extend(page)
    return rows


def _source_ids(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(
        sorted({value for value in values if isinstance(value, str) and value})
    )


def _appointment_end(payload: Mapping[str, Any]) -> datetime | None:
    value = payload.get("end_time") or payload.get("end_at")
    if not isinstance(value, str) or not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("appointment end time must be timezone-aware")
    return parsed


def technician_dispositions(
    *,
    provider: Mapping[str, Any],
    current_employees: Iterable[Mapping[str, Any]],
    workforce_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify exact provider identities without a name/email inference."""

    acquired_at = datetime.fromisoformat(
        str(provider["acquired_at"]).replace("Z", "+00:00")
    )
    if acquired_at.tzinfo is None:
        raise ValueError("provider acquisition time must be timezone-aware")
    employee_ids = {
        str(item["id"])
        for item in current_employees
        if isinstance(item.get("id"), str) and item["id"]
    }
    authority = {
        str(item["provider_employee_id"]): item
        for item in workforce_authority.get("records", [])
        if isinstance(item, dict) and item.get("provider_employee_id")
    }
    references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in provider.get("records", []):
        if not isinstance(record, dict) or record.get("domain") != "appointment":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise TypeError("provider Appointment payload is invalid")
        appointment_end = _appointment_end(payload)
        for source_id in _source_ids(payload.get("dispatched_employees_ids")):
            references[source_id].append(
                {
                    "appointment_id": record.get("source_id"),
                    "end_at": appointment_end.isoformat() if appointment_end else None,
                    "historical_at_acquisition": bool(
                        appointment_end and appointment_end < acquired_at
                    ),
                }
            )

    rows: list[dict[str, Any]] = []
    for source_id, appointments in sorted(references.items()):
        prior = authority.get(source_id)
        exact_current = source_id in employee_ids
        all_historical = bool(appointments) and all(
            item["historical_at_acquisition"] for item in appointments
        )
        if exact_current:
            disposition = "CURRENT_EMPLOYEE"
            safe_mapping = "EXACT_PROVIDER_EMPLOYEE_ID"
            reason = "identity is present in the sealed current HCP Employee collection"
        elif prior and prior.get("employment_status") == "TERMINATED":
            disposition = "FORMER_EMPLOYEE"
            safe_mapping = "RETAIN_SOURCE_ID_WITHOUT_ACTIVE_ASSIGNMENT"
            reason = "exact sealed workforce authority identifies a terminated employee"
        elif all_historical and prior is None:
            disposition = "PROVIDER_HISTORICAL_IDENTITY"
            safe_mapping = "RETAIN_SOURCE_ID_WITHOUT_PERSON_MAPPING"
            reason = "identity appears only on appointments ended before acquisition"
        else:
            disposition = "UNRESOLVED_HOLD"
            safe_mapping = None
            reason = (
                "current roster conflicts with prior active authority"
                if prior and prior.get("employment_status") == "ACTIVE"
                else "evidence does not prove a current/former person mapping"
            )
        rows.append(
            {
                "source_technician_id": source_id,
                "disposition": disposition,
                "safe_mapping": safe_mapping,
                "reason": reason,
                "current_employee_exact_id": exact_current,
                "prior_authority_exact_id": prior is not None,
                "prior_authority_status": prior.get("employment_status")
                if prior
                else None,
                "appointment_reference_count": len(appointments),
                "all_references_historical_at_acquisition": all_historical,
                "appointment_evidence": appointments,
            }
        )
    totals = dict(sorted(Counter(item["disposition"] for item in rows).items()))
    missing = [item for item in rows if not item["current_employee_exact_id"]]
    document: dict[str, Any] = {
        "contract": "hcp-technician-identity-disposition/v1",
        "acquired_at": provider["acquired_at"],
        "classification_rule": "exact source identity only; no name/email inference",
        "referenced_identity_count": len(rows),
        "absent_from_current_employee_count": len(missing),
        "totals": totals,
        "records": rows,
    }
    document["digest"] = canonical_digest(document)
    return document


def validate_gate_packet(
    gate_path: Path,
    *,
    workforce_authority_path: Path,
    final_policy_path: Path,
    expected_counts: Mapping[str, int] = EXPECTED_GATE_COUNTS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify every sealed byte and return a safe report plus technician packet."""

    require_private_file(gate_path)
    gate = load_object(gate_path)
    if gate.get("contract") != "hcp-operational-cutover-gate-packet/v1":
        raise ValueError("operational gate contract mismatch")
    gate_digest = verify_document_digest(gate, "operational gate")
    classification_count, classifications = _verify_classifications(gate)

    source_path = Path(str(gate["acquisition_manifest"]))
    require_private_file(source_path)
    source = load_object(source_path)
    source_digest = verify_document_digest(source, "acquisition manifest")
    if source_digest != gate.get("acquisition_manifest_digest"):
        raise ValueError("gate acquisition lineage mismatch")
    source_root = source_path.parent
    artifacts = _artifact_rows(source, source_root)
    if _raw_page_seal(artifacts) != source.get("raw_page_seal"):
        raise ValueError("acquisition raw-page seal mismatch")

    by_artifact = {row["artifact"]: row for row in artifacts}
    for collection, seal in source.get("collection_seals", {}).items():
        page_seals = seal.get("page_seals") if isinstance(seal, dict) else None
        if not isinstance(page_seals, list):
            raise TypeError(f"{collection} collection seal is invalid")
        if canonical_digest(page_seals) != seal.get("page_seal_digest"):
            raise ValueError(f"{collection} page-seal digest mismatch")
        if sum(int(row["record_count"]) for row in page_seals) != seal.get("count"):
            raise ValueError(f"{collection} collection count mismatch")
        for row in page_seals:
            artifact = by_artifact.get(row.get("artifact"))
            if artifact is None or artifact.get("sha256") != row.get("sha256"):
                raise ValueError(f"{collection} page seal is not in raw artifacts")

    addendum: dict[str, Any] | None = None
    addendum_path = gate.get("artifact_addendum")
    if addendum_path:
        path = Path(str(addendum_path))
        require_private_file(path)
        addendum = load_object(path)
        addendum_digest = verify_document_digest(addendum, "artifact addendum")
        if (
            addendum_digest != gate.get("artifact_addendum_digest")
            or addendum.get("source_manifest_digest") != source_digest
        ):
            raise ValueError("artifact addendum lineage mismatch")
        addendum_artifacts = _artifact_rows(addendum, path.parent)
        if _raw_page_seal(addendum_artifacts) != addendum.get("raw_page_seal"):
            raise ValueError("artifact addendum raw-page seal mismatch")

    custody: dict[str, Any] | None = None
    custody_path = gate.get("attachment_custody")
    if custody_path:
        path = Path(str(custody_path))
        require_private_file(path)
        custody = load_object(path)
        custody_digest = verify_document_digest(custody, "attachment custody")
        if (
            custody_digest != gate.get("attachment_custody_digest")
            or addendum is None
            or custody.get("source_artifact_addendum_digest") != addendum.get("digest")
        ):
            raise ValueError("attachment custody lineage mismatch")
        content_rows = _artifact_rows(custody, path.parent, content=True)
        if _raw_content_seal(content_rows) != custody.get("raw_content_seal"):
            raise ValueError("attachment content seal mismatch")

    provider_path = Path(str(gate["provider_observations"]))
    require_private_file(provider_path)
    provider = load_object(provider_path)
    provider_digest = verify_document_digest(provider, "provider observations")
    if (
        provider_digest != gate.get("provider_observations_digest")
        or provider.get("source_manifest_digest") != source_digest
    ):
        raise ValueError("provider observation lineage mismatch")
    provider_keys: set[tuple[str, str]] = set()
    for row in provider.get("records", []):
        key = (str(row.get("domain")), str(row.get("source_id")))
        if key in provider_keys or not all(key):
            raise ValueError("provider observation identity is duplicate/invalid")
        provider_keys.add(key)
        if canonical_digest(row.get("payload")) != row.get("source_digest"):
            raise ValueError(f"provider source digest mismatch: {key[0]}:{key[1]}")

    final_policy, final_policy_digest = validate_final_policy(
        final_policy_path,
        gate=gate,
        gate_digest=gate_digest,
    )
    explicit_holds = required_operational_holds(
        gate=gate,
        provider=provider,
        final_policy=final_policy,
    )
    hold_closure = operational_hold_closure(provider, explicit_holds)
    hold_domains = dict(sorted(Counter(domain for domain, _ in hold_closure).items()))
    if (
        len(hold_closure)
        != EXPECTED_OPERATIONAL_POLICY_HOLDS["with_parent_cascade"]
        or any(
            hold_domains.get(domain) != expected
            for domain, expected in EXPECTED_OPERATIONAL_POLICY_HOLDS.items()
            if domain not in {"explicit", "with_parent_cascade"}
        )
    ):
        raise ValueError("final operational hold closure mismatch")

    workforce = load_object(workforce_authority_path)
    technicians = technician_dispositions(
        provider=provider,
        current_employees=_pages(source_root, "employees", "employees"),
        workforce_authority=workforce,
    )
    coverage = source.get("coverage", {})
    holds = gate.get("unresolved_holds", {})
    operational_counts = _provider_operational_counts(provider)
    observed_counts = {
        **operational_counts,
        "employees": coverage.get("employees"),
        "missing_technicians": holds.get(
            "technician_identities_absent_from_current_employees"
        ),
        "locationless_jobs": holds.get("locationless_open_jobs"),
        "legacy_appointments": holds.get("legacy_appointment_duplicate_risk"),
        "holds": classifications.get("HOLD", 0),
        "attachments": custody.get("count") if custody else None,
    }
    if observed_counts != dict(expected_counts):
        raise ValueError(f"fresh gate count mismatch: {observed_counts}")
    if (
        technicians["absent_from_current_employee_count"]
        != expected_counts["missing_technicians"]
    ):
        raise ValueError("technician identity accounting mismatch")
    if not (
        custody
        and custody.get("state") == "COMPLETE"
        and holds.get("attachments_content_custody_complete") is True
    ):
        raise ValueError("attachment custody is incomplete")

    report: dict[str, Any] = {
        "contract": "hcp-operational-cutover-gate-validation/v1",
        "status": "VALID",
        "gate_digest": gate_digest,
        "source_manifest_digest": source_digest,
        "provider_observations_digest": provider_digest,
        "raw_page_seal": source["raw_page_seal"],
        "artifact_addendum_digest": addendum.get("digest") if addendum else None,
        "attachment_custody_digest": custody.get("digest") if custody else None,
        "attachment_content_seal": custody.get("raw_content_seal") if custody else None,
        "acquired_at": source["acquisition"]["completed_at"],
        "company": source["company"],
        "counts": observed_counts,
        "appointment_relationship_failures": 0,
        "appointment_transport_statuses": coverage.get("appointment_http_statuses"),
        "classification_count": classification_count,
        "classification_totals": classifications,
        "technician_disposition_digest": technicians["digest"],
        "final_policy_digest": final_policy_digest,
        "explicit_operational_hold_count": len(explicit_holds),
        "operational_hold_count_with_parent_cascade": len(hold_closure),
        "operational_hold_counts_by_domain": hold_domains,
        "operational_hold_set_digest": canonical_digest(
            [
                {"domain": domain, "source_id": source_id}
                for domain, source_id in sorted(hold_closure)
            ]
        ),
    }
    report["digest"] = canonical_digest(report)
    return report, technicians
