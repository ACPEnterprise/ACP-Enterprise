"""Read-only Customer history projection from sealed HCP SOURCE.4 evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-customer-source-history/v1"


class HcpCustomerSourceHistoryError(ValueError):
    pass


def _rows(root: Path, family: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / family).glob("page-*.json")):
        value = json.loads(path.read_bytes())
        page = value.get(family)
        if not isinstance(page, list):
            raise HcpCustomerSourceHistoryError(f"invalid_{family}_page")
        rows.extend(item for item in page if isinstance(item, dict))
    if not rows:
        raise HcpCustomerSourceHistoryError(f"missing_{family}_evidence")
    return rows


@lru_cache(maxsize=2)
def _source_indexes(
    root_text: str, manifest_sha256: str
) -> tuple[
    dict[str, tuple[dict[str, Any], ...]],
    dict[str, tuple[dict[str, Any], ...]],
]:
    # The manifest digest is intentionally part of the cache key. Deployments mount
    # this evidence read-only; a newly sealed package receives a new digest.
    del manifest_sha256
    root = Path(root_text)
    estimates_by_customer: dict[str, list[dict[str, Any]]] = {}
    for estimate in _rows(root, "estimates"):
        customer_id = (estimate.get("customer") or {}).get("id")
        if isinstance(customer_id, str):
            estimates_by_customer.setdefault(customer_id, []).append(estimate)
    job_customers = {
        str(job["id"]): (job.get("customer") or {}).get("id")
        for job in _rows(root, "jobs")
    }
    invoices_by_customer: dict[str, list[dict[str, Any]]] = {}
    for invoice in _rows(root, "invoices"):
        customer_id = job_customers.get(str(invoice.get("job_id")))
        if isinstance(customer_id, str):
            invoices_by_customer.setdefault(customer_id, []).append(invoice)
    return (
        {key: tuple(value) for key, value in estimates_by_customer.items()},
        {key: tuple(value) for key, value in invoices_by_customer.items()},
    )


def project_customer_source_history(
    root: Path, *, source_customer_id: str
) -> dict[str, object]:
    """Project exact provider-linked history without creating Accounting truth."""
    manifest_path = root / "acquisition-package-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise HcpCustomerSourceHistoryError("unsupported_source_package")
    if manifest.get("request_methods") != ["GET"]:
        raise HcpCustomerSourceHistoryError("source_package_not_read_only")

    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    estimates_by_customer, invoices_by_customer = _source_indexes(
        str(root.resolve()), manifest_sha256
    )
    estimates = estimates_by_customer.get(source_customer_id, ())
    invoices = invoices_by_customer.get(source_customer_id, ())

    estimate_items = []
    for estimate in sorted(estimates, key=lambda row: str(row.get("id"))):
        options = estimate.get("options")
        option_rows = options if isinstance(options, list) else []
        estimate_items.append(
            {
                "source_id": estimate.get("id"),
                "number": estimate.get("estimate_number"),
                "status": estimate.get("work_status"),
                "created_at": estimate.get("created_at"),
                "updated_at": estimate.get("updated_at"),
                "options": [
                    {
                        "source_id": option.get("id"),
                        "name": option.get("name"),
                        "amount_cents": option.get("total_amount"),
                    }
                    for option in option_rows
                    if isinstance(option, Mapping)
                ],
                "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
            }
        )

    payment_count = 0
    invoice_items = []
    for invoice in sorted(invoices, key=lambda row: str(row.get("id"))):
        raw_payments = invoice.get("payments")
        payments = raw_payments if isinstance(raw_payments, list) else []
        payment_items = []
        for payment in payments:
            if not isinstance(payment, Mapping):
                continue
            payment_count += 1
            imported_qbo = payment.get("payment_method") == "imported_from_quickbooks"
            payment_items.append(
                {
                    "source_id": payment.get("id"),
                    "status": payment.get("status"),
                    "amount_cents": payment.get("amount"),
                    "date": payment.get("created_at") or payment.get("paid_at"),
                    "payment_method": payment.get("payment_method"),
                    "overlap_disposition": (
                        "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION"
                        if imported_qbo
                        else "HCP_ONLY_SOURCE_EVIDENCE"
                    ),
                    "authority": "HCP_SOURCE_BACKED_PAYMENT_EVIDENCE_NOT_ACCOUNTING_POSTING",
                }
            )
        invoice_items.append(
            {
                "source_id": invoice.get("id"),
                "source_job_id": invoice.get("job_id"),
                "number": invoice.get("invoice_number"),
                "status": invoice.get("status"),
                "amount_cents": invoice.get("amount"),
                "balance_cents": invoice.get("due_amount"),
                "invoice_date": invoice.get("invoice_date"),
                "service_date": invoice.get("service_date"),
                "payments": payment_items,
                "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
            }
        )

    return {
        "contract": CONTRACT,
        "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "source_customer_id": source_customer_id,
        "source_manifest_sha256": manifest_sha256,
        "counts": {
            "estimates": len(estimate_items),
            "invoices": len(invoice_items),
            "payments": payment_count,
        },
        "estimates": estimate_items,
        "invoices": invoice_items,
    }
