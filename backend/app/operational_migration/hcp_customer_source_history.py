"""Read-only Customer history projection from sealed HCP SOURCE.4 evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

CONTRACT: Final = "hcp-customer-source-history/v3"


class HcpCustomerSourceHistoryError(ValueError):
    pass


def _rows(root: Path, family: str, *, required: bool = True) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "raw" / family).glob("*.json")):
        value = json.loads(path.read_bytes())
        page = value.get(family)
        if not isinstance(page, list):
            raise HcpCustomerSourceHistoryError(f"invalid_{family}_page")
        for item in page:
            if isinstance(item, dict):
                rows.append(
                    {**item, "_parent_job_id": path.stem.removeprefix("job-")}
                    if family == "appointments" and path.stem.startswith("job-")
                    else item
                )
    if required and not rows:
        raise HcpCustomerSourceHistoryError(f"missing_{family}_evidence")
    return rows


@lru_cache(maxsize=2)
def _source_indexes(
    root_text: str, manifest_sha256: str
) -> dict[str, dict[str, tuple[dict[str, Any], ...]]]:
    # The manifest digest is intentionally part of the cache key. Deployments mount
    # this evidence read-only; a newly sealed package receives a new digest.
    del manifest_sha256
    root = Path(root_text)
    customers_by_id = {str(row["id"]): row for row in _rows(root, "customers")}
    jobs_by_customer: dict[str, list[dict[str, Any]]] = {}
    jobs_by_id: dict[str, dict[str, Any]] = {}
    for job in _rows(root, "jobs"):
        job_id = str(job["id"])
        jobs_by_id[job_id] = job
        customer_id = (job.get("customer") or {}).get("id")
        if isinstance(customer_id, str):
            jobs_by_customer.setdefault(customer_id, []).append(job)
    estimates_by_customer: dict[str, list[dict[str, Any]]] = {}
    for estimate in _rows(root, "estimates"):
        customer_id = (estimate.get("customer") or {}).get("id")
        if isinstance(customer_id, str):
            estimates_by_customer.setdefault(customer_id, []).append(estimate)
    appointments_by_customer: dict[str, list[dict[str, Any]]] = {}
    for appointment in _rows(root, "appointments", required=False):
        job = jobs_by_id.get(str(appointment.get("_parent_job_id")))
        customer_id = (job.get("customer") or {}).get("id") if job else None
        if isinstance(customer_id, str):
            appointments_by_customer.setdefault(customer_id, []).append(appointment)
    invoices_by_customer: dict[str, list[dict[str, Any]]] = {}
    for invoice in _rows(root, "invoices"):
        job = jobs_by_id.get(str(invoice.get("job_id")))
        customer_id = (job.get("customer") or {}).get("id") if job else None
        if isinstance(customer_id, str):
            invoices_by_customer.setdefault(customer_id, []).append(invoice)
    return {
        "customers": {key: (value,) for key, value in customers_by_id.items()},
        "jobs": {key: tuple(value) for key, value in jobs_by_customer.items()},
        "appointments": {
            key: tuple(value) for key, value in appointments_by_customer.items()
        },
        "estimates": {
            key: tuple(value) for key, value in estimates_by_customer.items()
        },
        "invoices": {key: tuple(value) for key, value in invoices_by_customer.items()},
    }


def project_customer_source_history(
    root: Path, *, source_customer_id: str
) -> dict[str, object]:
    """Project exact provider-linked history without creating Accounting truth."""
    manifest_path = root / "acquisition-package-manifest.json"
    if not manifest_path.exists():
        manifest_path = root / "current-source-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract") not in {
        "hcp-source-4-acquisition-package/v1",
        "hcp-current-provider-acquisition/v1",
    }:
        raise HcpCustomerSourceHistoryError("unsupported_source_package")
    if not (
        manifest.get("request_methods") == ["GET"]
        or manifest.get("policy") == "GET_ONLY"
    ):
        raise HcpCustomerSourceHistoryError("source_package_not_read_only")

    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    indexes = _source_indexes(str(root.resolve()), manifest_sha256)
    customer_rows = indexes["customers"].get(source_customer_id, ())
    jobs = indexes["jobs"].get(source_customer_id, ())
    appointments = indexes["appointments"].get(source_customer_id, ())
    estimates = indexes["estimates"].get(source_customer_id, ())
    invoices = indexes["invoices"].get(source_customer_id, ())
    if len(customer_rows) != 1:
        raise HcpCustomerSourceHistoryError("exact_source_customer_unavailable")
    customer = customer_rows[0]

    location_items = [
        {
            "source_id": item.get("id"),
            "address": item.get("street") or item.get("address"),
            "city": item.get("city"),
            "state": item.get("state"),
            "postal_code": item.get("zip") or item.get("postal_code"),
            "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
        }
        for item in customer.get("addresses") or []
        if isinstance(item, Mapping) and item.get("id")
    ]
    job_items = [
        {
            "source_id": job.get("id"),
            "source_location_id": (job.get("address") or {}).get("id"),
            "number": job.get("invoice_number") or job.get("job_number"),
            "status": job.get("work_status") or job.get("status"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "scheduled_start": job.get("start_time"),
            "scheduled_end": job.get("end_time"),
            "assigned_employee_source_ids": [
                str(item.get("id"))
                for item in job.get("assigned_employees") or []
                if isinstance(item, Mapping) and item.get("id")
            ],
            "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
        }
        for job in sorted(jobs, key=lambda row: str(row.get("id")))
    ]
    appointment_items = [
        {
            "source_id": item.get("id"),
            "source_job_id": item.get("_parent_job_id"),
            "scheduled_start": item.get("start_time") or item.get("start_date"),
            "scheduled_end": item.get("end_time"),
            "assigned_employee_source_ids": list(
                item.get("dispatched_employees_ids") or []
            ),
            "authority": "HCP_SOURCE_BACKED_OPERATIONAL_HISTORY",
        }
        for item in sorted(appointments, key=lambda row: str(row.get("id")))
    ]

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
    refund_count = 0
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
        raw_refunds = invoice.get("refunds")
        refunds = raw_refunds if isinstance(raw_refunds, list) else []
        refund_items = []
        for refund in refunds:
            if not isinstance(refund, Mapping):
                continue
            refund_count += 1
            refund_items.append(
                {
                    "source_id": refund.get("id"),
                    "status": refund.get("status"),
                    "amount_cents": refund.get("amount"),
                    "date": refund.get("refunded_at"),
                    "payment_method": refund.get("payment_method"),
                    "identity_disposition": (
                        "EXACT_PROVIDER_REFUND_ID"
                        if refund.get("id")
                        else "SOURCE_BACKED_UNLINKED_REFUND"
                    ),
                    "aggregation_safe": False,
                    "authority": "HCP_SOURCE_BACKED_REFUND_EVIDENCE_NOT_ACCOUNTING_POSTING",
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
                "refunds": refund_items,
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
            "locations": len(location_items),
            "jobs": len(job_items),
            "appointments": len(appointment_items),
            "estimates": len(estimate_items),
            "invoices": len(invoice_items),
            "payments": payment_count,
            "refunds": refund_count,
        },
        "locations": location_items,
        "jobs": job_items,
        "appointments": appointment_items,
        "estimates": estimate_items,
        "invoices": invoice_items,
    }
