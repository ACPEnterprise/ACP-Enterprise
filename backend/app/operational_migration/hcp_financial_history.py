"""Deterministic HCP Invoice and payment-history evidence classification.

This module reads sealed provider evidence only.  Its output is suitable for a
source-backed history projection; it never promotes HCP evidence to ACP-native
Accounting truth and explicitly isolates assertions imported from QBO.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-financial-history-classification/v2"


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _collection(root: Path, name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / name).glob("page-*.json")):
        value = json.loads(path.read_bytes())
        records.extend(value[name])
    return records


@dataclass(frozen=True)
class FinancialHistoryClassification:
    contract: str
    source_manifest_sha256: str
    invoice_counts: dict[str, int]
    payment_counts: dict[str, int]
    refund_counts: dict[str, int]
    payment_records: tuple[dict[str, Any], ...]
    refund_records: tuple[dict[str, Any], ...]
    authority: dict[str, str]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        digest = payload.pop("digest")
        if self.contract != CONTRACT or digest != _canonical_digest(payload):
            raise ValueError("financial history classification digest mismatch")


def classify_financial_history(source_root: Path) -> FinancialHistoryClassification:
    manifest_path = source_root / "acquisition-package-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise ValueError("unsupported HCP source package")
    if manifest.get("request_methods") != ["GET"]:
        raise ValueError("HCP source package is not read-only")

    jobs = _collection(source_root, "jobs")
    invoices = _collection(source_root, "invoices")
    job_ids = {str(record["id"]) for record in jobs}
    if len(job_ids) != len(jobs):
        raise ValueError("duplicate HCP Job source identity")
    invoice_ids = {str(record["id"]) for record in invoices}
    if len(invoice_ids) != len(invoices):
        raise ValueError("duplicate HCP Invoice source identity")

    invoice_statuses = Counter(str(record.get("status")) for record in invoices)
    parent_resolved = sum(record.get("job_id") in job_ids for record in invoices)
    parent_missing = len(invoices) - parent_resolved

    payments = [
        (invoice, payment)
        for invoice in invoices
        for payment in invoice.get("payments", [])
    ]
    payment_ids = [str(payment.get("id") or "") for _, payment in payments]
    if not all(payment_ids) or len(payment_ids) != len(set(payment_ids)):
        raise ValueError("missing or duplicate HCP Payment source identity")
    payment_statuses = Counter(str(payment.get("status")) for _, payment in payments)
    qbo_overlap = sum(
        payment.get("payment_method") == "imported_from_quickbooks"
        for _, payment in payments
    )
    refunds = [
        (invoice, refund)
        for invoice in invoices
        for refund in invoice.get("refunds", [])
    ]

    payment_records = tuple(
        {
            "source_payment_id": str(payment["id"]),
            "source_invoice_id": str(invoice["id"]),
            "status": str(payment.get("status")),
            "payment_method": str(payment.get("payment_method")),
            "amount": payment.get("amount"),
            "paid_at": payment.get("paid_at"),
            "source_origin": "HCP",
            "qbo_origin_asserted": payment.get("payment_method")
            == "imported_from_quickbooks",
            "exact_qbo_provider_identity": None,
            "disposition": (
                "SOURCE_DISPLAYABLE_NONAGGREGATED"
                if payment.get("payment_method") == "imported_from_quickbooks"
                else (
                    "HCP_ONLY" if payment.get("status") == "succeeded" else "UNRESOLVED"
                )
            ),
            "display_authority": (
                "SOURCE_BACKED_NOT_ACCOUNTING_POSTING"
                if payment.get("status") == "succeeded"
                else "FAILED_SOURCE_ASSERTION"
            ),
            "aggregation_safe": False,
        }
        for invoice, payment in sorted(payments, key=lambda item: str(item[1]["id"]))
    )
    refund_records = tuple(
        {
            "source_refund_id": refund.get("id"),
            "source_invoice_id": str(invoice["id"]),
            "status": str(refund.get("status")),
            "payment_method": str(refund.get("payment_method")),
            "amount": refund.get("amount"),
            "refunded_at": refund.get("refunded_at"),
            "disposition": (
                "EXACT_REFUND" if refund.get("id") else "SOURCE_BACKED_UNLINKED_REFUND"
            ),
            "display_authority": "SOURCE_BACKED_NOT_ACCOUNTING_POSTING",
            "aggregation_safe": False,
        }
        for invoice, refund in sorted(
            refunds,
            key=lambda item: (
                str(item[0]["id"]),
                str(item[1].get("id") or ""),
                str(item[1].get("refunded_at") or ""),
            ),
        )
    )

    invoice_counts = {
        "source_acquired": len(invoices),
        "source_graph_complete": parent_resolved,
        "source_parent_missing": parent_missing,
        **{f"status_{key}": value for key, value in sorted(invoice_statuses.items())},
    }
    payment_counts = {
        "source_acquired": len(payments),
        "source_invoice_exact": len(payments),
        "source_backed_displayable": payment_statuses["succeeded"],
        "failed_assertion": payment_statuses["failed"],
        "qbo_overlap_hold": qbo_overlap,
        "hcp_only_displayable": payment_statuses["succeeded"] - qbo_overlap,
        "exact_qbo_overlap": 0,
        "qbo_only": 0,
        "source_displayable_nonaggregated": qbo_overlap,
        "conflicting": 0,
        "unresolved": payment_statuses["failed"],
    }
    refund_counts = {
        "source_acquired": len(refunds),
        "exact_refund": sum(bool(refund.get("id")) for _, refund in refunds),
        "source_backed_unlinked_refund": sum(
            not refund.get("id") for _, refund in refunds
        ),
        "conflicting": 0,
        "source_missing": 0,
    }
    authority = {
        "invoice": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
        "payment": "HCP_SOURCE_BACKED_PAYMENT_EVIDENCE_NOT_ACCOUNTING_POSTING",
        "qbo_overlap": "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION",
        "mutation_authority": "none",
    }
    source_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    payload = {
        "contract": CONTRACT,
        "source_manifest_sha256": source_manifest_sha256,
        "invoice_counts": invoice_counts,
        "payment_counts": payment_counts,
        "refund_counts": refund_counts,
        "payment_records": payment_records,
        "refund_records": refund_records,
        "authority": authority,
    }
    return FinancialHistoryClassification(
        contract=CONTRACT,
        source_manifest_sha256=source_manifest_sha256,
        invoice_counts=invoice_counts,
        payment_counts=payment_counts,
        refund_counts=refund_counts,
        payment_records=payment_records,
        refund_records=refund_records,
        authority=authority,
        digest=_canonical_digest(payload),
    )
