"""Adapt the sealed November admissible-records packet for bounded execution.

The source packet is an immutable classification artifact.  This adapter never
rewrites it; it creates a deterministic executor packet while retaining the
source locator and lineage metadata on every derived record.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import (
    PACKET_CONTRACT,
    _digest,
)


SOURCE_PACKET_CONTRACT = "hcp-november-bounded-admissible-records/v1"
ADAPTER_VERSION = "hcp-november-bounded-admissible-records-adapter/v1"
SOURCE_DOMAINS = frozenset(
    {
        "appointment",
        "attachment",
        "customer",
        "employee",
        "estimate",
        "invoice",
        "job",
        "legacy_appointment",
        "note",
        "service_location",
        "technician_reference",
    }
)
DISPOSITIONS = frozenset({"CREATE", "UPDATE", "REPLAY", "HOLD", "HOLD_QUARANTINE"})
EXPECTED_COUNTS = {
    "CREATE": 511,
    "UPDATE": 823,
    "REPLAY": 3857,
    "HOLD": 2079,
    "HOLD_QUARANTINE": 23,
}


def _fail(code: str, value: object = "") -> None:
    raise SafeEvidenceError(code, _digest(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_source_digest(source: dict[str, Any]) -> str:
    payload = dict(source)
    payload.pop("digest", None)
    return _digest(payload)


def _require_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code, value)
    return value


def _require_digest(value: Any, code: str) -> str:
    value = _require_text(value, code)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        _fail(code, value)
    return value


def _scope(source: dict[str, Any], expected: dict[str, str]) -> None:
    scope = source.get("scope")
    if not isinstance(scope, dict) or scope.get("target") != "preview":
        _fail("hcp_november_adapter_scope_invalid", scope)
    actual = {
        "company_id": scope.get("company_id"),
        "branch_id": scope.get("branch_id"),
        "actor_id": scope.get("actor_id"),
        "provider_company_id": scope.get("provider_company_id"),
    }
    if actual != expected:
        _fail("hcp_november_adapter_scope_mismatch", {"expected": expected, "actual": actual})


def _parent_keys(
    record: dict[str, Any],
    records_by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, str]]:
    lineage = record.get("parent_lineage")
    if not isinstance(lineage, list):
        _fail("hcp_november_adapter_lineage_missing", record.get("domain"))
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for parent in lineage:
        if not isinstance(parent, dict):
            _fail("hcp_november_adapter_lineage_invalid", parent)
        domain = _require_text(parent.get("domain"), "hcp_november_adapter_parent_domain_missing")
        source_id = _require_text(parent.get("source_id"), "hcp_november_adapter_parent_identity_missing")
        key = (domain, source_id)
        if key in seen or key not in records_by_key:
            _fail("hcp_november_adapter_lineage_ambiguous", key)
        seen.add(key)
        source_parent = records_by_key[key]
        if parent.get("disposition") != source_parent.get("disposition"):
            _fail("hcp_november_adapter_lineage_disposition_mismatch", key)
        result.append({"domain": domain, "source_id": source_id})
    return result


def adapt_source_packet(
    source: dict[str, Any],
    *,
    source_packet_sha256: str,
    expected_source_packet_sha256: str,
    expected_source_packet_digest: str,
    qualification_digest: str,
    repository_sha: str,
    schema_head: str,
    expected_scope: dict[str, str],
    expected_operational_hold_source_ids: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, Any]:
    """Return a derived executor packet without modifying ``source``."""

    if source.get("contract") != SOURCE_PACKET_CONTRACT:
        _fail("hcp_november_adapter_source_contract", source.get("contract"))
    if source_packet_sha256 != expected_source_packet_sha256:
        _fail("hcp_november_adapter_source_sha256_mismatch", source_packet_sha256)
    if source.get("digest") != expected_source_packet_digest:
        _fail("hcp_november_adapter_source_digest_declaration_mismatch", source.get("digest"))
    if _canonical_source_digest(source) != expected_source_packet_digest:
        _fail("hcp_november_adapter_source_digest_mismatch", source.get("digest"))
    if not qualification_digest or len(qualification_digest) != 64:
        _fail("hcp_november_adapter_qualification_digest_invalid", qualification_digest)
    if len(repository_sha) != 40 or any(char not in "0123456789abcdef" for char in repository_sha):
        _fail("hcp_november_adapter_repository_sha_invalid", repository_sha)
    if schema_head != "yp8r0t2v4x6z":
        _fail("hcp_november_adapter_schema_head_invalid", schema_head)
    _scope(source, expected_scope)

    sealed = source.get("sealed_inputs")
    if not isinstance(sealed, dict):
        _fail("hcp_november_adapter_sealed_inputs_missing")
    bundle_sha256 = _require_digest(sealed.get("admission_bundle_sha256"), "hcp_november_adapter_bundle_digest_invalid")
    policy_digest = _require_digest(sealed.get("policy_digest"), "hcp_november_adapter_policy_digest_invalid")
    reconciliation_digest = _require_digest(sealed.get("reconciliation_digest"), "hcp_november_adapter_reconciliation_digest_invalid")

    raw_records = source.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        _fail("hcp_november_adapter_records_missing")
    records_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in raw_records:
        if not isinstance(record, dict):
            _fail("hcp_november_adapter_record_invalid", record)
        domain = _require_text(record.get("domain"), "hcp_november_adapter_domain_missing")
        source_id = _require_text(record.get("source_id"), "hcp_november_adapter_identity_missing")
        if domain not in SOURCE_DOMAINS:
            _fail("hcp_november_adapter_unknown_domain", domain)
        key = (domain, source_id)
        if key in records_by_key:
            _fail("hcp_november_adapter_duplicate_identity", key)
        records_by_key[key] = record

    acquired_at = _require_text(source.get("acquired_at"), "hcp_november_adapter_acquired_at_missing")
    derived_records: list[dict[str, Any]] = []
    for record in raw_records:
        domain = str(record["domain"])
        source_id = str(record["source_id"])
        disposition = str(record.get("disposition", "")).upper()
        if disposition not in DISPOSITIONS:
            _fail("hcp_november_adapter_unknown_disposition", disposition)
        executable = record.get("executable")
        if not isinstance(executable, bool):
            _fail("hcp_november_adapter_executable_flag_missing", (domain, source_id))
        if executable != (disposition in {"CREATE", "UPDATE", "REPLAY"}):
            _fail("hcp_november_adapter_disposition_executable_mismatch", (domain, source_id))
        parents = _parent_keys(record, records_by_key)
        parent_keys = {(item["domain"], item["source_id"]) for item in parents}
        if disposition in {"CREATE", "UPDATE", "REPLAY"}:
            for parent_key in parent_keys:
                if str(records_by_key[parent_key].get("disposition", "")).upper() in {"HOLD", "HOLD_QUARANTINE"}:
                    _fail("hcp_november_adapter_held_parent_executable_edge", (domain, source_id))
        source_digest = _require_digest(record.get("source_digest"), "hcp_november_adapter_record_digest_invalid")
        prior = record.get("prior_source_digest")
        if prior is not None:
            prior = _require_digest(prior, "hcp_november_adapter_prior_digest_invalid")
        if disposition == "UPDATE" and prior is None:
            _fail("hcp_november_adapter_update_lineage_missing", (domain, source_id))
        locator = _require_text(record.get("payload_locator"), "hcp_november_adapter_payload_locator_missing")
        assertion = "hold" if disposition in {"HOLD", "HOLD_QUARANTINE"} else ("update" if disposition == "UPDATE" else "create")
        derived_records.append(
            {
                "domain": domain,
                "source_id": source_id,
                "assertion": assertion,
                "source_digest": source_digest,
                "acquired_at": acquired_at,
                "payload": {} if assertion == "hold" else {"payload_locator": locator},
                "prior_source_digest": prior,
                "parent_keys": parents,
                "native_fingerprint": None,
                "reason": str(record.get("reason") or record.get("hold_subdisposition") or ""),
                "disposition": disposition,
                "payload_locator": locator,
                "parent_lineage": record.get("parent_lineage"),
                "execution_phase": record.get("execution_phase"),
                "hold_subdisposition": record.get("hold_subdisposition"),
                "original_gate_disposition": record.get("original_gate_disposition"),
                "source_executable": executable,
            }
        )

    counts = {key: sum(item["disposition"] == key for item in derived_records) for key in DISPOSITIONS}
    if counts != EXPECTED_COUNTS:
        _fail("hcp_november_adapter_count_mismatch", counts)
    if source.get("classification_totals") != EXPECTED_COUNTS:
        _fail("hcp_november_adapter_count_mismatch", source.get("classification_totals"))
    held = {item["source_id"] for item in derived_records if item["disposition"] in {"HOLD", "HOLD_QUARANTINE"}}
    executable = {item["source_id"] for item in derived_records if item["disposition"] in {"CREATE", "UPDATE", "REPLAY"}}
    if len(held) != 2102 or len(executable) != 5191 or len(derived_records) != 7293:
        _fail("hcp_november_adapter_inventory_mismatch", {"held": len(held), "executable": len(executable), "total": len(derived_records)})
    summary = source.get("summary")
    if not isinstance(summary, dict) or summary.get("unexplained_omissions") != [] or summary.get("lineage_gaps") != []:
        _fail("hcp_november_adapter_qualification_gap", summary)
    if summary.get("held_identity_count") != 2102 or summary.get("executable_record_count") != 5191:
        _fail("hcp_november_adapter_summary_mismatch", summary)
    if expected_operational_hold_source_ids is not None:
        expected_hold_keys = {
            "locationless_open_jobs": ("job", "HOLD_QUARANTINE"),
            "duplicate_risk_appointments": ("appointment", "HOLD"),
            "unresolved_technician_identities": ("technician_reference", "HOLD"),
            "unassigned_appointments": ("appointment", "HOLD"),
        }
        if set(expected_operational_hold_source_ids) != set(expected_hold_keys):
            _fail("hcp_november_adapter_operational_hold_categories_invalid")
        by_key = {(item["domain"], item["source_id"]): item["disposition"] for item in derived_records}
        for category, source_ids in expected_operational_hold_source_ids.items():
            domain, disposition = expected_hold_keys[category]
            if any(by_key.get((domain, source_id)) != disposition for source_id in source_ids):
                _fail("hcp_november_adapter_operational_hold_source_mismatch", category)

    payload = {
        "contract": PACKET_CONTRACT,
        "qualification_digest": qualification_digest,
        "bundle_sha256": bundle_sha256,
        "policy_digest": policy_digest,
        "reconciliation_digest": reconciliation_digest,
        "company_id": expected_scope["company_id"],
        "branch_id": expected_scope["branch_id"],
        "actor_id": expected_scope["actor_id"],
        "provider_company_id": expected_scope["provider_company_id"],
        "schema_head": schema_head,
        "environment": "preview",
        "records": sorted(derived_records, key=lambda item: (item["domain"], item["source_id"])),
        "acquired_at": acquired_at,
    }
    payload["digest"] = _digest(payload)
    return payload


def adapt_packet_file(
    source_path: Path,
    output_path: Path,
    **kwargs: str,
) -> tuple[str, str]:
    """Write a mode-0600 derived packet and return (source_sha, derived_sha)."""

    if source_path.is_symlink() or not source_path.is_file():
        _fail("hcp_november_adapter_source_missing", str(source_path))
    source_sha = _sha256(source_path)
    source = json.loads(source_path.read_bytes())
    derived = adapt_source_packet(source, source_packet_sha256=source_sha, **kwargs)
    if output_path.exists():
        _fail("hcp_november_adapter_output_conflict", str(output_path))
    output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.name + ".tmp")
    tmp.write_text(json.dumps(derived, sort_keys=True, separators=(",", ":")))
    os.chmod(tmp, 0o600)
    os.replace(tmp, output_path)
    return source_sha, _sha256(output_path)
