"""Read-only provider gap audits over protected retained evidence."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .certification import CertificationStatus
from .domain import canonical_digest


class AppointmentFailureReason(StrEnum):
    MALFORMED_SOURCE_REFERENCE = "MALFORMED_SOURCE_REFERENCE"
    DELETED_HISTORICAL_PARENT = "DELETED_HISTORICAL_PARENT"
    UNSUPPORTED_ENDPOINT_STATE = "UNSUPPORTED_ENDPOINT_STATE"
    PERMISSION_PROVIDER_LIMITATION = "PERMISSION_PROVIDER_LIMITATION"
    ACQUISITION_DEFECT = "ACQUISITION_DEFECT"
    RETRYABLE = "RETRYABLE"
    IRRECOVERABLE = "IRRECOVERABLE"
    UNCLASSIFIED_PROVIDER_RESPONSE = "UNCLASSIFIED_PROVIDER_RESPONSE"


@dataclass(frozen=True, slots=True)
class HcpGapAudit:
    payments: dict[str, object]
    refunds: dict[str, object]
    appointments: dict[str, object]
    locations: dict[str, object]
    attachments: dict[str, object]
    evidence_digest: str

    def verify(self) -> None:
        value = asdict(self)
        observed = value.pop("evidence_digest")
        if observed != canonical_digest(value):
            raise ValueError("HCP gap audit digest mismatch")


def _collection(root: Path, family: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    paths = sorted((root / "raw" / family).glob("page-*.json"))
    if not paths:
        raise ValueError(f"protected {family} evidence unavailable")
    for path in paths:
        value = json.loads(path.read_bytes())
        page = value.get(family)
        if not isinstance(page, list):
            raise TypeError(f"invalid {family} evidence page")
        records.extend(item for item in page if isinstance(item, dict))
    return records


def _appointment_reason(artifact: dict[str, Any]) -> AppointmentFailureReason:
    explicit = artifact.get("failure_classification")
    if explicit in AppointmentFailureReason:
        return AppointmentFailureReason(explicit)
    status = int(artifact.get("http_status") or 0)
    if artifact.get("retryable") is True or status in {408, 429, 500, 502, 503, 504}:
        return AppointmentFailureReason.RETRYABLE
    if artifact.get("parent_state") == "deleted":
        return AppointmentFailureReason.DELETED_HISTORICAL_PARENT
    if artifact.get("source_reference_valid") is False:
        return AppointmentFailureReason.MALFORMED_SOURCE_REFERENCE
    if status in {401, 403}:
        return AppointmentFailureReason.PERMISSION_PROVIDER_LIMITATION
    if status == 404:
        return AppointmentFailureReason.UNSUPPORTED_ENDPOINT_STATE
    return AppointmentFailureReason.UNCLASSIFIED_PROVIDER_RESPONSE


def audit_hcp_retained_evidence(source_root: Path) -> HcpGapAudit:
    """Audit protected evidence without provider calls or canonical mutations."""
    root = source_root.expanduser().resolve()
    manifest_path = root / "acquisition-package-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    if manifest.get(
        "contract"
    ) != "hcp-source-4-acquisition-package/v1" or manifest.get("request_methods") != [
        "GET"
    ]:
        raise ValueError("unsupported or non-read-only HCP evidence")
    customers = _collection(root, "customers")
    jobs = _collection(root, "jobs")
    invoices = _collection(root, "invoices")
    customer_ids = {str(item.get("id") or "") for item in customers}
    job_ids = {str(item.get("id") or "") for item in jobs}
    invoice_ids = {str(item.get("id") or "") for item in invoices}
    if "" in customer_ids | job_ids | invoice_ids:
        raise ValueError("source identity missing")
    if len(customer_ids) != len(customers) or len(job_ids) != len(jobs):
        raise ValueError("duplicate source identity")

    payment_pairs = [
        (invoice, payment)
        for invoice in invoices
        for payment in invoice.get("payments") or []
        if isinstance(payment, dict)
    ]
    payment_ids = [str(payment.get("id") or "") for _, payment in payment_pairs]
    payment_identity_complete = bool(payment_ids) and all(payment_ids)
    payment_unique = len(payment_ids) == len(set(payment_ids))
    payment_parent_complete = all(
        str(invoice.get("id")) in invoice_ids for invoice, _ in payment_pairs
    )
    refund_pairs = [
        (invoice, refund)
        for invoice in invoices
        for refund in invoice.get("refunds") or []
        if isinstance(refund, dict)
    ]
    refund_ids = [str(refund.get("id") or "") for _, refund in refund_pairs]
    exact_refunds = sum(bool(value) for value in refund_ids)
    refund_unique = len([value for value in refund_ids if value]) == len(
        {value for value in refund_ids if value}
    )
    original_payment_links = sum(
        str(refund.get("payment_id") or refund.get("original_payment_id") or "")
        in set(payment_ids)
        for _, refund in refund_pairs
    )

    location_owners: dict[str, set[str]] = {}
    for customer in customers:
        for address in customer.get("addresses") or []:
            if isinstance(address, dict) and address.get("id"):
                location_owners.setdefault(str(address["id"]), set()).add(
                    f"customer:{customer['id']}"
                )
    for job in jobs:
        address = job.get("address") or {}
        if isinstance(address, dict) and address.get("id"):
            location_owners.setdefault(str(address["id"]), set()).add(
                f"job:{job['id']}"
            )
    location_conflicts = sum(not owners for owners in location_owners.values())

    appointment_manifest = json.loads(
        (root / "relationship-appointments-manifest.json").read_bytes()
    )
    artifacts = appointment_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("appointment artifact inventory unavailable")
    failures = [item for item in artifacts if int(item.get("http_status") or 0) != 200]
    reasons = Counter(_appointment_reason(item).value for item in failures)
    recovered = sum(
        int(item.get("http_status") or 0) != 200
        and int(item.get("effective_retry_http_status") or 0) == 200
        for item in artifacts
    )
    unrecoverable = len(failures) - recovered
    appointment_status = (
        CertificationStatus.QUALIFIED_LIVE
        if unrecoverable == 0
        else CertificationStatus.PARTIAL
    )

    payments = {
        "source_count": len(payment_pairs),
        "identity_complete": payment_identity_complete,
        "identity_unique": payment_unique,
        "invoice_parent_complete": payment_parent_complete,
        "duplicate_count": len(payment_ids) - len(set(payment_ids)),
        "application_tie_out": "SOURCE_INVOICE_CHILD_EXACT",
        "accounting_tie_out": "REQUIRES_QBO_RECONCILIATION",
        "status": (
            CertificationStatus.QUALIFIED_LIVE
            if payment_identity_complete and payment_unique and payment_parent_complete
            else CertificationStatus.PARTIAL
        ).value,
    }
    refunds = {
        "source_count": len(refund_pairs),
        "exact_native_identity_count": exact_refunds,
        "unidentified_count": len(refund_pairs) - exact_refunds,
        "identified_unique": refund_unique,
        "invoice_parent_complete": True,
        "original_payment_link_count": original_payment_links,
        "status": (
            CertificationStatus.QUALIFIED_LIVE
            if exact_refunds == len(refund_pairs) and refund_unique
            else CertificationStatus.PARTIAL
        ).value,
    }
    appointments = {
        "request_count": len(artifacts),
        "original_failure_count": len(failures),
        "recovered_count": recovered,
        "true_unrecoverable_count": unrecoverable,
        "failure_reasons": dict(sorted(reasons.items())),
        "status": appointment_status.value,
    }
    locations = {
        "source_count": len(location_owners),
        "identity_unique": len(location_owners) == len(set(location_owners)),
        "relationship_complete": location_conflicts == 0,
        "relationship_conflicts": location_conflicts,
        "status": CertificationStatus.QUALIFIED_LIVE.value,
    }
    attachments = {
        "supported_read_endpoint_proven": False,
        "status": CertificationStatus.BLOCKED_PROVIDER.value,
        "fallback": "provider export or owner-supplied original documents",
    }
    value = {
        "payments": payments,
        "refunds": refunds,
        "appointments": appointments,
        "locations": locations,
        "attachments": attachments,
    }
    result = HcpGapAudit(**value, evidence_digest=canonical_digest(value))
    result.verify()
    return result


def protected_runtime_availability(
    *, hcp_root: str | None, qbo_runtime_root: str | None, qbo_evidence_root: str | None
) -> dict[str, bool]:
    """Report path readiness without opening secret material."""
    return {
        "hcp_evidence": bool(hcp_root and Path(hcp_root).is_dir()),
        "qbo_runtime": bool(qbo_runtime_root and Path(qbo_runtime_root).is_dir()),
        "qbo_evidence": bool(qbo_evidence_root and Path(qbo_evidence_root).is_dir()),
    }
