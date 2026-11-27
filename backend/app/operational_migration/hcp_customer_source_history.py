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


def _job_details(root: Path) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for path in sorted((root / "raw" / "job-details").glob("*.json")):
        value = json.loads(path.read_bytes())
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            details[value["id"]] = value
    return details


def _customers_with_job_snapshots(root: Path) -> list[dict[str, Any]]:
    """Include exact provider Customer snapshots embedded in Job details.

    HCP can return a Job whose Customer is absent from the paginated Customer
    collection.  The embedded object is source evidence, not an inferred
    identity, so it is safe to expose as historical-only data while retaining
    the missing-collection distinction.
    """
    by_id = {
        str(row["id"]): row
        for row in _rows(root, "customers")
        if isinstance(row.get("id"), str)
    }
    for detail in _job_details(root).values():
        customer = detail.get("customer")
        if isinstance(customer, Mapping) and isinstance(customer.get("id"), str):
            by_id.setdefault(str(customer["id"]), dict(customer))
    return list(by_id.values())


def _attachment_rows(
    root: Path, attachment_root: Path | None
) -> dict[str, tuple[dict[str, Any], ...]]:
    manifest_path = root / "attachment-custody-manifest.json"
    if not manifest_path.exists() and attachment_root is not None:
        manifest_path = attachment_root / "attachment-custody-manifest.json"
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_bytes())
    conflicts = {
        str(item.get("attachment_id")): item
        for item in manifest.get("conflicts", [])
        if isinstance(item, Mapping) and item.get("attachment_id")
    }
    by_job: dict[str, list[dict[str, Any]]] = {}
    for item in manifest.get("attachments", []):
        if not isinstance(item, Mapping) or not item.get("source_id"):
            continue
        source_id = str(item["source_id"])
        conflict = conflicts.get(source_id)
        artifact = str(item.get("artifact") or "")
        body_available = bool(
            attachment_root
            and artifact
            and (attachment_root / artifact).is_file()
            and item.get("status") == "RECOVERED"
            and conflict is None
        )
        row = {
            "source_id": source_id,
            "file_name": item.get("file_name"),
            "file_type": item.get("file_type"),
            "size_bytes": item.get("size_bytes"),
            "content_sha256": item.get("content_sha256"),
            "status": "UNRESOLVED" if conflict else item.get("status"),
            "body_available": body_available,
            "conflict_reason": conflict.get("reason") if conflict else None,
            "view_url": (
                f"/api/v1/migration/source-history/attachments/{source_id}"
                if body_available
                else None
            ),
        }
        job_id = item.get("job_id")
        if isinstance(job_id, str):
            by_job.setdefault(job_id, []).append(row)
    for conflict in conflicts.values():
        source_id = str(conflict["attachment_id"])
        if any(
            row.get("source_id") == source_id
            for rows in by_job.values()
            for row in rows
        ):
            continue
        job_id = conflict.get("job_id")
        if isinstance(job_id, str):
            by_job.setdefault(job_id, []).append(
                {
                    "source_id": source_id,
                    "file_name": None,
                    "file_type": None,
                    "size_bytes": None,
                    "content_sha256": None,
                    "status": "UNRESOLVED",
                    "body_available": False,
                    "conflict_reason": conflict.get("reason"),
                    "view_url": None,
                }
            )
    return {key: tuple(value) for key, value in by_job.items()}


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
    root_text: str, manifest_sha256: str, attachment_root_text: str | None
) -> dict[str, dict[str, tuple[dict[str, Any], ...]]]:
    # The manifest digest is intentionally part of the cache key. Deployments mount
    # this evidence read-only; a newly sealed package receives a new digest.
    del manifest_sha256
    root = Path(root_text)
    customers_by_id = {
        str(row["id"]): row for row in _customers_with_job_snapshots(root)
    }
    jobs_by_customer: dict[str, list[dict[str, Any]]] = {}
    jobs_by_id: dict[str, dict[str, Any]] = {}
    details = _job_details(root)
    for source_job in _rows(root, "jobs"):
        job_id = str(source_job["id"])
        merged_job = {**source_job, **details.get(job_id, {})}
        jobs_by_id[job_id] = merged_job
        customer_id = (merged_job.get("customer") or {}).get("id")
        if isinstance(customer_id, str):
            jobs_by_customer.setdefault(customer_id, []).append(merged_job)
    estimates_by_customer: dict[str, list[dict[str, Any]]] = {}
    for estimate in _rows(root, "estimates"):
        customer_id = (estimate.get("customer") or {}).get("id")
        if isinstance(customer_id, str):
            estimates_by_customer.setdefault(customer_id, []).append(estimate)
    appointments_by_customer: dict[str, list[dict[str, Any]]] = {}
    job_hashes = {
        hashlib.sha256(job_id.encode()).hexdigest(): job_id for job_id in jobs_by_id
    }
    for path in sorted((root / "raw" / "appointments").glob("*.json")):
        value = json.loads(path.read_bytes())
        parent_job_id = next(
            (job_id for digest, job_id in job_hashes.items() if digest in path.stem),
            None,
        )
        for appointment in value.get("appointments", []):
            if not isinstance(appointment, dict):
                continue
            appointment = {**appointment, "_parent_job_id": parent_job_id}
            parent_job = jobs_by_id.get(str(parent_job_id))
            customer_id = (
                (parent_job.get("customer") or {}).get("id") if parent_job else None
            )
            if isinstance(customer_id, str):
                appointments_by_customer.setdefault(customer_id, []).append(appointment)
    invoices_by_customer: dict[str, list[dict[str, Any]]] = {}
    for invoice in _rows(root, "invoices"):
        parent_job = jobs_by_id.get(str(invoice.get("job_id")))
        customer_id = (
            (parent_job.get("customer") or {}).get("id") if parent_job else None
        )
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
        "attachments": _attachment_rows(
            root, Path(attachment_root_text) if attachment_root_text else None
        ),
    }


def project_customer_source_history(
    root: Path,
    *,
    source_customer_id: str,
    attachment_root: Path | None = None,
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
    indexes = _source_indexes(
        str(root.resolve()),
        manifest_sha256,
        str(attachment_root.resolve()) if attachment_root else None,
    )
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
            "scheduled_start": (job.get("schedule") or {}).get("scheduled_start")
            or job.get("start_time"),
            "scheduled_end": (job.get("schedule") or {}).get("scheduled_end")
            or job.get("end_time"),
            "service_date": (job.get("schedule") or {}).get("scheduled_start")
            or job.get("start_time"),
            "description": job.get("description"),
            "notes": [
                {
                    "source_id": note.get("id"),
                    "content": note.get("content"),
                }
                for note in job.get("notes") or []
                if isinstance(note, Mapping)
            ],
            "work_timestamps": job.get("work_timestamps") or {},
            "original_estimate_id": job.get("original_estimate_id"),
            "original_estimate_ids": list(job.get("original_estimate_uuids") or []),
            "invoice_number": job.get("invoice_number"),
            "total_amount": job.get("total_amount"),
            "outstanding_balance": job.get("outstanding_balance"),
            "assigned_employee_source_ids": [
                str(item.get("id"))
                for item in job.get("assigned_employees") or []
                if isinstance(item, Mapping) and item.get("id")
            ],
            "attachments": list(indexes["attachments"].get(str(job.get("id")), ())),
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


def search_customer_source_history(
    root: Path, *, query: str, limit: int = 20
) -> dict[str, object]:
    """Search sealed source Customers without requiring native admission."""
    normalized = " ".join(query.casefold().split())
    if len(normalized) < 2:
        raise HcpCustomerSourceHistoryError("search_query_too_short")
    if not 1 <= limit <= 50:
        raise HcpCustomerSourceHistoryError("search_limit_invalid")

    manifest_path = root / "acquisition-package-manifest.json"
    if not manifest_path.exists():
        manifest_path = root / "current-source-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if not (
        manifest.get("request_methods") == ["GET"]
        or manifest.get("policy") == "GET_ONLY"
    ):
        raise HcpCustomerSourceHistoryError("source_package_not_read_only")

    matches: list[dict[str, object]] = []
    for customer in _customers_with_job_snapshots(root):
        addresses = [
            address
            for address in customer.get("addresses") or []
            if isinstance(address, Mapping)
        ]
        display_name = (
            customer.get("display_name")
            or customer.get("company")
            or " ".join(
                str(value).strip()
                for value in (customer.get("first_name"), customer.get("last_name"))
                if value
            )
            or "Name unavailable"
        )
        searchable = " ".join(
            [
                str(customer.get("id") or ""),
                str(display_name),
                str(customer.get("email") or ""),
                str(customer.get("mobile_number") or customer.get("phone") or ""),
                *[
                    " ".join(
                        str(address.get(field) or "")
                        for field in ("street", "address", "city", "state", "zip")
                    )
                    for address in addresses
                ],
            ]
        ).casefold()
        if normalized not in searchable:
            continue
        matches.append(
            {
                "source_customer_id": str(customer["id"]),
                "display_name": str(display_name),
                "primary_location": (
                    ", ".join(
                        str(addresses[0].get(field)).strip()
                        for field in ("street", "address", "city", "state", "zip")
                        if addresses[0].get(field)
                    )
                    if addresses
                    else None
                ),
                "authority": "HCP_SOURCE_BACKED_HISTORICAL_CUSTOMER",
                "accepted_as_native": False,
            }
        )
    ordered = sorted(
        matches,
        key=lambda item: (
            str(item["display_name"]).casefold(),
            str(item["source_customer_id"]),
        ),
    )
    return {
        "contract": "hcp-customer-source-search/v1",
        "authority": "HCP_SOURCE_BACKED_HISTORICAL_CUSTOMER",
        "mutation_authority": "none",
        "query": query,
        "items": ordered[:limit],
        "match_count": len(ordered),
        "limited": len(ordered) > limit,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
