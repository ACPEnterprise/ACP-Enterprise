"""Read-only HCP/QBO financial reconciliation and acceptance evidence.

The analyzer deliberately keeps provider evidence in separate authority lanes.
It does not match on names, dates, or amounts and never treats source evidence
as an ACP Accounting posting.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-qbo-financial-reconciliation-readiness/v1"
JOURNEY_COUNT: Final = 50


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _collection(root: Path, name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / name).glob("page-*.json")):
        page = json.loads(path.read_bytes())
        records.extend(page[name])
    return records


def _verified_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    return value, hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class FinancialReconciliationReadiness:
    contract: str
    source_manifest_sha256: str
    ar_control_sha256: str
    ar_readiness: dict[str, object]
    may_report_evidence: dict[str, object]
    journey_counts: dict[str, int]
    journeys: tuple[dict[str, object], ...]
    accountant_exceptions: dict[str, object]
    authority: dict[str, object]
    digest: str

    def verify(self) -> None:
        payload = asdict(self)
        expected = payload.pop("digest")
        if self.contract != CONTRACT or expected != _digest(payload):
            raise ValueError("financial reconciliation readiness digest mismatch")


def build_financial_reconciliation_readiness(
    *,
    source_root: Path,
    qbo_controls_root: Path,
) -> FinancialReconciliationReadiness:
    """Build deterministic, non-mutating financial readiness evidence."""

    manifest_path = source_root / "acquisition-package-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise ValueError("unsupported HCP source package")
    if manifest.get("request_methods") != ["GET"]:
        raise ValueError("HCP source package is not read-only")

    customers = _collection(source_root, "customers")
    jobs = _collection(source_root, "jobs")
    estimates = _collection(source_root, "estimates")
    invoices = _collection(source_root, "invoices")
    customer_ids = {str(item["id"]) for item in customers}
    jobs_by_id = {str(item["id"]): item for item in jobs}
    if len(customer_ids) != len(customers) or len(jobs_by_id) != len(jobs):
        raise ValueError("duplicate HCP Customer or Job identity")

    estimates_by_customer: defaultdict[str, list[str]] = defaultdict(list)
    for estimate in estimates:
        customer_id = str((estimate.get("customer") or {}).get("id") or "")
        if customer_id:
            estimates_by_customer[customer_id].append(str(estimate["id"]))

    invoices_by_customer: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_parent_invoice_ids: list[str] = []
    qbo_overlap_payment_ids: list[str] = []
    missing_refund_provider_identity: list[dict[str, str]] = []
    hcp_open_balance_cents = 0
    for invoice in invoices:
        job = jobs_by_id.get(str(invoice.get("job_id") or ""))
        if job is None:
            missing_parent_invoice_ids.append(str(invoice["id"]))
        else:
            customer_id = str((job.get("customer") or {}).get("id") or "")
            if customer_id in customer_ids:
                invoices_by_customer[customer_id].append(invoice)
        if invoice.get("status") == "open":
            hcp_open_balance_cents += int(invoice.get("due_amount") or 0)
        for payment in invoice.get("payments", []):
            if payment.get("payment_method") == "imported_from_quickbooks":
                qbo_overlap_payment_ids.append(str(payment["id"]))
        for ordinal, refund in enumerate(invoice.get("refunds", []), start=1):
            if not refund.get("id"):
                missing_refund_provider_identity.append(
                    {"invoice_source_id": str(invoice["id"]), "ordinal": str(ordinal)}
                )

    journeys = _journeys(
        customer_ids=customer_ids,
        estimates_by_customer=estimates_by_customer,
        invoices_by_customer=invoices_by_customer,
    )
    journey_counts = dict(
        sorted(Counter(str(item["classification"]) for item in journeys).items())
    )

    ar_path = qbo_controls_root / "qbo-cutoff-ar-aging-control-2026-08-31-v1.json"
    ar_control, ar_sha256 = _verified_json(ar_path)
    if ar_control.get("schema_version") != "qbo-ar-aging-control-analysis/v1":
        raise ValueError("unsupported QBO A/R control")
    expected_ar_digest = ar_control.get("evidence_digest")
    digest_payload = dict(ar_control)
    digest_payload.pop("evidence_digest", None)
    if expected_ar_digest != _digest(digest_payload):
        raise ValueError("QBO A/R control semantic digest mismatch")

    type_balances = ar_control.get("type_open_balances") or {}
    invoice_open = str(type_balances.get("Invoice") or "0")
    payment_open = str(type_balances.get("Payment") or "0")
    deposit_open = str(type_balances.get("Deposit") or "0")
    ar_readiness: dict[str, object] = {
        "gross_open_ready": True,
        "gross_open_qbo_invoice_balance": invoice_open,
        "gross_open_hcp_assertion_balance": str(
            (Decimal(hcp_open_balance_cents) / Decimal(100)).quantize(Decimal("0.01"))
        ),
        "credits_ready": False,
        "unapplied_ready": False,
        "net_ar_ready": False,
        "reconciliation_required": True,
        "qbo_payment_open_evidence": payment_open,
        "qbo_deposit_open_evidence": deposit_open,
        "qbo_report_net_open_balance": str(ar_control["open_balance"]),
        "reason": (
            "QBO aging supplies exact gross and negative source rows, but payment/"
            "deposit application and ledger-tie authority remain unresolved"
        ),
    }

    may_report_evidence = _may_evidence(qbo_controls_root)
    accountant_exceptions: dict[str, object] = {
        "hcp_invoices_missing_source_job": {
            "count": len(missing_parent_invoice_ids),
            "source_ids": sorted(missing_parent_invoice_ids),
        },
        "qbo_imported_hcp_payments_held_from_aggregation": {
            "count": len(qbo_overlap_payment_ids),
            "source_ids": sorted(qbo_overlap_payment_ids),
        },
        "refunds_missing_provider_identity": {
            "count": len(missing_refund_provider_identity),
            "records": sorted(
                missing_refund_provider_identity,
                key=lambda item: (item["invoice_source_id"], item["ordinal"]),
            ),
        },
        "ar_controls": {
            "negative_open_item_count": ar_control["negative_open_item_count"],
            "cutoff_to_current_variance": ar_control["cutoff_to_current_variance"],
            "ledger_tie_required": True,
            "payment_application_authority_required": True,
        },
        "rules": {
            "weak_field_matching_permitted": False,
            "hcp_qbo_aggregation_permitted": False,
            "accounting_posting_authorized": False,
        },
    }
    authority: dict[str, object] = {
        "classification": "SOURCE_BACKED_RECONCILIATION_EVIDENCE",
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "matching_basis": "EXACT_PROVIDER_SOURCE_GRAPH_ONLY",
    }
    payload = {
        "contract": CONTRACT,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "ar_control_sha256": ar_sha256,
        "ar_readiness": ar_readiness,
        "may_report_evidence": may_report_evidence,
        "journey_counts": journey_counts,
        "journeys": tuple(journeys),
        "accountant_exceptions": accountant_exceptions,
        "authority": authority,
    }
    return FinancialReconciliationReadiness(
        contract=CONTRACT,
        source_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        ar_control_sha256=ar_sha256,
        ar_readiness=ar_readiness,
        may_report_evidence=may_report_evidence,
        journey_counts=journey_counts,
        journeys=tuple(journeys),
        accountant_exceptions=accountant_exceptions,
        authority=authority,
        digest=_digest(payload),
    )


def _journeys(
    *,
    customer_ids: set[str],
    estimates_by_customer: dict[str, list[str]],
    invoices_by_customer: dict[str, list[dict[str, Any]]],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for customer_id in sorted(customer_ids & invoices_by_customer.keys()):
        invoices = invoices_by_customer[customer_id]
        payment_ids = sorted(
            str(payment["id"])
            for invoice in invoices
            for payment in invoice.get("payments", [])
        )
        refund_refs = sorted(
            str(refund.get("id") or f'{invoice["id"]}:unidentified-refund')
            for invoice in invoices
            for refund in invoice.get("refunds", [])
        )
        overlap = any(
            payment.get("payment_method") == "imported_from_quickbooks"
            for invoice in invoices
            for payment in invoice.get("payments", [])
        )
        estimate_ids = sorted(estimates_by_customer.get(customer_id, []))
        if overlap:
            classification = "FINANCIAL_OVERLAP_HOLD"
        elif estimate_ids and payment_ids:
            classification = "COMPLETE_SOURCE_HISTORY"
        else:
            classification = "PARTIAL_SOURCE_HISTORY"
        candidates.append(
            {
                "customer_source_id": customer_id,
                "estimate_source_ids": estimate_ids,
                "invoice_source_ids": sorted(str(invoice["id"]) for invoice in invoices),
                "payment_source_ids": payment_ids,
                "refund_source_references": refund_refs,
                "open_invoice_source_ids": sorted(
                    str(invoice["id"])
                    for invoice in invoices
                    if invoice.get("status") == "open"
                ),
                "classification": classification,
                "authority": "HCP_SOURCE_BACKED_NOT_ACCOUNTING_POSTING",
            }
        )
    rank = {
        "COMPLETE_SOURCE_HISTORY": 0,
        "FINANCIAL_OVERLAP_HOLD": 1,
        "PARTIAL_SOURCE_HISTORY": 2,
    }
    candidates.sort(key=lambda item: (rank[str(item["classification"])], item["customer_source_id"]))
    if len(candidates) < JOURNEY_COUNT:
        raise ValueError("fewer than 50 exact Customer financial journeys")
    return candidates[:JOURNEY_COUNT]


def _may_evidence(root: Path) -> dict[str, object]:
    registrations: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        value = json.loads(path.read_bytes())
        if value.get("schema_version") == "qbo-control-registration/v1":
            registrations.append(value)
    may_pnl = [
        item
        for item in registrations
        if item.get("kind") == "profit_and_loss"
        and (item.get("safe_report_parameters") or {}).get("start_date")
        == "2026-05-01"
        and (item.get("safe_report_parameters") or {}).get("end_date")
        == "2026-05-31"
        and item.get("accounting_basis") == "cash"
    ]
    general_ledger = [item for item in registrations if item.get("kind") == "general_ledger"]
    return {
        "provider_may_profit_and_loss_registered": bool(may_pnl),
        "may_profit_and_loss_control_ids": sorted(
            str(item["control_id"]) for item in may_pnl
        ),
        "general_ledger_controls_present": len(general_ledger),
        "general_ledger_is_not_profit_and_loss": True,
        "broad_profit_and_loss_may_not_be_sliced_as_provider_report": True,
        "required_external_acquisition": None
        if may_pnl
        else "QBO ProfitAndLoss 2026-05-01..2026-05-31 CASH",
    }
