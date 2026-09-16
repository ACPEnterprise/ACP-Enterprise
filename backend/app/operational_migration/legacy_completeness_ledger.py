"""Deterministic, read-only legacy replacement completeness ledger."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "migration-legacy-replacement-completeness-ledger/v1"
FAMILIES: Final = (
    "customers",
    "locations",
    "jobs",
    "appointments",
    "estimates",
    "invoices",
    "payments",
    "refunds",
    "employees",
    "attachments",
    "qbo_control_reports",
    "accounting_source_evidence",
)
COUNT_FIELDS: Final = (
    "source_acquired",
    "source_bound",
    "native_admitted",
    "operationally_projected",
    "source_backed_only",
    "held",
    "owner_decision_required",
    "accountant_decision_required",
    "provider_unsupported",
    "source_missing",
    "unresolved",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _collection(source_root: Path, family: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((source_root / "raw" / family).glob("page-*.json")):
        records.extend(_load(path)[family])
    return records


def _empty_counts() -> dict[str, int | None]:
    return dict.fromkeys(COUNT_FIELDS)


@dataclass(frozen=True)
class LegacyCompletenessLedger:
    contract: str
    families: dict[str, dict[str, object]]
    evidence: dict[str, str]
    invariants: dict[str, object]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        observed = payload.pop("digest")
        if self.contract != CONTRACT or observed != hashlib.sha256(_canonical(payload)).hexdigest():
            raise ValueError("legacy completeness ledger digest mismatch")
        if tuple(sorted(self.families)) != tuple(sorted(FAMILIES)):
            raise ValueError("legacy completeness ledger family coverage mismatch")
        for family in self.families.values():
            counts = family["counts"]
            if not isinstance(counts, dict):
                raise TypeError("legacy completeness ledger counts must be a mapping")
            if set(counts) != set(COUNT_FIELDS):
                raise ValueError("legacy completeness ledger count coverage mismatch")


def build_legacy_completeness_ledger(
    *,
    source_root: Path,
    job_appointment_readiness_path: Path,
    estimate_readiness_path: Path,
    employee_packet_path: Path,
    attachment_packet_path: Path,
    qbo_controls_root: Path,
    native_binding_snapshot_path: Path | None = None,
) -> LegacyCompletenessLedger:
    manifest_path = source_root / "acquisition-package-manifest.json"
    manifest = _load(manifest_path)
    if manifest.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise ValueError("unsupported HCP source package")
    if manifest.get("request_methods") != ["GET"]:
        raise ValueError("HCP package is not read-only")

    customers = _collection(source_root, "customers")
    jobs = _collection(source_root, "jobs")
    estimates = _collection(source_root, "estimates")
    invoices = _collection(source_root, "invoices")
    employees = _collection(source_root, "employees")
    location_ids = {
        str(address["id"])
        for customer in customers
        for address in customer.get("addresses") or []
        if address.get("id")
    }
    location_ids.update(
        str(address["id"])
        for job in jobs
        if (address := job.get("address") or {}).get("id")
    )
    payments = [payment for invoice in invoices for payment in invoice.get("payments") or []]
    refunds = [refund for invoice in invoices for refund in invoice.get("refunds") or []]

    graph = _load(job_appointment_readiness_path)
    estimate_readiness = _load(estimate_readiness_path)
    employee_packet = _load(employee_packet_path)
    attachment_packet = _load(attachment_packet_path)
    if graph.get("contract") != "hcp-source4-job-appointment-history-readiness/v1":
        raise ValueError("unsupported Job/Appointment readiness")
    if estimate_readiness.get("contract") != "hcp-source4-estimate-history-readiness/v1":
        raise ValueError("unsupported Estimate readiness")
    if employee_packet.get("contract") != "hcp-employee-owner-certification/v1":
        raise ValueError("unsupported employee packet")
    if attachment_packet.get("contract") != "hcp-open-work-attachment-export-request/v1":
        raise ValueError("unsupported attachment packet")

    native_counts: dict[str, dict[str, int]] | None = None
    snapshot_sha: str | None = None
    if native_binding_snapshot_path is not None:
        snapshot = _load(native_binding_snapshot_path)
        snapshot_sha = _sha(native_binding_snapshot_path)
        native_counts = snapshot.get("family_counts")
        if not isinstance(native_counts, dict):
            raise ValueError("native binding snapshot lacks family_counts")

    registrations = []
    for path in sorted(qbo_controls_root.glob("*.json")):
        value = _load(path)
        if value.get("schema_version") == "qbo-control-registration/v1":
            registrations.append(value)

    payment_methods = Counter(str(item.get("payment_method") or "") for item in payments)
    payment_statuses = Counter(str(item.get("status") or "") for item in payments)
    refund_with_id = sum(bool(item.get("id")) for item in refunds)
    graph_counts = graph["counts"]
    estimate_counts = estimate_readiness["counts"]["candidate_dispositions"]

    families: dict[str, dict[str, object]] = {}

    def add(
        name: str,
        *,
        acquired: int,
        source_backed: int | None = None,
        held: int | None = None,
        owner: int | None = None,
        accountant: int | None = None,
        unsupported: int | None = None,
        missing: int | None = None,
        unresolved: int | None = None,
        notes: tuple[str, ...] = (),
    ) -> None:
        counts = _empty_counts()
        counts.update(
            source_acquired=acquired,
            source_backed_only=source_backed,
            held=held,
            owner_decision_required=owner,
            accountant_decision_required=accountant,
            provider_unsupported=unsupported,
            source_missing=missing,
            unresolved=unresolved,
        )
        if native_counts and name in native_counts:
            values = native_counts[name]
            counts["source_bound"] = values.get("source_bound")
            counts["native_admitted"] = values.get("native_admitted")
            counts["operationally_projected"] = values.get("operationally_projected")
        families[name] = {
            "counts": counts,
            "native_state_evidence": "AVAILABLE" if native_counts else "UNAVAILABLE_NOT_ZERO",
            "notes": notes,
        }

    add("customers", acquired=len(customers), notes=("native counts require sanctioned post-admission binding snapshot",))
    add("locations", acquired=len(location_ids), notes=("identity is provider address ID only; address matching is forbidden",))
    add(
        "jobs",
        acquired=len(jobs),
        source_backed=graph_counts["jobs"]["SOURCE_GRAPH_READY"],
        held=graph_counts["jobs"]["LOCATION_SOURCE_MISSING"],
        unresolved=graph_counts["jobs"]["LOCATION_SOURCE_MISSING"],
    )
    add(
        "appointments",
        acquired=graph_counts["appointments"]["total"],
        source_backed=graph_counts["appointments"]["SOURCE_GRAPH_READY"],
        held=graph_counts["appointments"]["PARENT_LOCATION_SOURCE_MISSING"],
        unresolved=graph_counts["appointment_relationships"]["PROVIDER_RELATIONSHIP_ERROR"],
    )
    add(
        "estimates",
        acquired=len(estimates),
        source_backed=len(estimates),
        held=estimate_counts["SAFE_ADMIT_BINDING_DEPENDENT"],
        owner=estimate_counts["OWNER_DECISION_REQUIRED"],
        unresolved=estimate_counts["SAFE_ADMIT_BINDING_DEPENDENT"],
    )
    job_ids = {str(job["id"]) for job in jobs}
    missing_job = sum(str(invoice.get("job_id") or "") not in job_ids for invoice in invoices)
    add("invoices", acquired=len(invoices), source_backed=len(invoices), held=missing_job, missing=missing_job, unresolved=missing_job)
    imported = payment_methods["imported_from_quickbooks"]
    failed = payment_statuses["failed"]
    add("payments", acquired=len(payments), source_backed=len(payments), held=imported, accountant=imported, unresolved=failed)
    add("refunds", acquired=len(refunds), source_backed=len(refunds), held=len(refunds) - refund_with_id, accountant=len(refunds) - refund_with_id, unresolved=len(refunds) - refund_with_id)
    add("employees", acquired=employee_packet["record_count"], source_backed=employee_packet["record_count"], held=employee_packet["record_count"], owner=employee_packet["record_count"], unresolved=employee_packet["record_count"], notes=(f"sealed package employees={len(employees)}; current certification packet employees={employee_packet['record_count']}",))
    add("attachments", acquired=attachment_packet["acquired_attachment_metadata_count"], unsupported=attachment_packet["job_count"], missing=attachment_packet["job_count"], unresolved=attachment_packet["job_count"], notes=("absence is not authoritative; HCP UI/Support export required",))
    add("qbo_control_reports", acquired=len(registrations), source_backed=len(registrations), unresolved=0, notes=("QBO_SOURCE_BACKED; accepted_as_acp_accounting=false",))
    add("accounting_source_evidence", acquired=len(registrations), source_backed=len(registrations), notes=("control reports are evidence, not native ledger postings",))

    evidence = {
        "hcp_source_manifest_sha256": _sha(manifest_path),
        "job_appointment_readiness_sha256": _sha(job_appointment_readiness_path),
        "estimate_readiness_sha256": _sha(estimate_readiness_path),
        "employee_packet_sha256": _sha(employee_packet_path),
        "attachment_packet_sha256": _sha(attachment_packet_path),
        "native_binding_snapshot_sha256": snapshot_sha or "UNAVAILABLE",
    }
    invariants: dict[str, object] = {
        "connected_successfully_equals_migration_complete": False,
        "fuzzy_matching_permitted": False,
        "destructive_replacement_permitted": False,
        "hcp_qbo_silent_aggregation_permitted": False,
        "qbo_mutation_count": 0,
        "production_mutation_count": 0,
        "unavailable_counts_are_zero": False,
    }
    payload = {"contract": CONTRACT, "families": families, "evidence": evidence, "invariants": invariants}
    result = LegacyCompletenessLedger(
        contract=CONTRACT,
        families=families,
        evidence=evidence,
        invariants=invariants,
        digest=hashlib.sha256(_canonical(payload)).hexdigest(),
    )
    result.verify()
    return result
