from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from .bounded_evidence import (
    BoundedEvidenceError,
    latest_bounded_evidence,
    load_bounded_raw_rows,
)

Basis = Literal["cash", "accrual"]
_MAX_ROWS_PER_FAMILY = 2000


class QboEvidenceProjectionError(RuntimeError):
    pass


def unavailable_qbo_workspace(*, basis: Basis, limitation: str) -> dict[str, object]:
    unavailable = {"amount": None, "currency": None, "state": "unavailable"}
    return {
        "contract_version": "qbo-accounting-evidence/v1",
        "source": "quickbooks_online",
        "mode": "blocked",
        "provider_environment": "production",
        "company_identity_sha256": None,
        "company_info_verified_at": None,
        "source_manifest_sha256": None,
        "source_company_label": "Real company not verified",
        "source_company_id_masked": "unavailable",
        "accounting_basis": basis,
        "as_of": None,
        "acquired_at": None,
        "refresh_state": "unavailable",
        "provider_authorization": "unverified",
        "evidence_mode": "unavailable",
        "completeness": "unavailable",
        "entity_counts": {},
        "page_counts": {},
        "catalog_dispositions": [],
        "conflicts": [],
        "snapshot_id": None,
        "snapshot_digest": None,
        "is_live": False,
        "limitations": [limitation, "missing_values_are_not_zero"],
        "accounts": [],
        "invoices": [],
        "ar": {
            "total_open": unavailable,
            "current": unavailable,
            "overdue": unavailable,
        },
        "payments": [],
        "vendors": [],
        "bills": [],
        "reports": [],
        "mutation_authority": "none",
    }


def project_latest_qbo_workspace(
    *, evidence_root: Path, basis: Basis, runtime_root: Path | None = None
) -> dict[str, object]:
    """Project a bounded sealed production snapshot without creating native truth."""
    root = evidence_root.expanduser().resolve()
    if not root.is_dir():
        return unavailable_qbo_workspace(
            basis=basis, limitation="production_qbo_evidence_unavailable"
        )
    try:
        run = latest_bounded_evidence(root)
    except BoundedEvidenceError as error:
        raise QboEvidenceProjectionError(str(error)) from error
    if run is None:
        return unavailable_qbo_workspace(
            basis=basis, limitation="sealed_production_snapshot_unavailable"
        )
    manifest_path, manifest = run.manifest_path, run.manifest
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, Mapping) or snapshot.get("environment") != "production":
        raise QboEvidenceProjectionError("non_production_snapshot_rejected")
    state = str(manifest.get("state"))
    try:
        rows, truncated = load_bounded_raw_rows(
            run, maximum_per_family=_MAX_ROWS_PER_FAMILY
        )
    except BoundedEvidenceError as error:
        raise QboEvidenceProjectionError(str(error)) from error
    authorization_marker = _verify_current_authorization(
        runtime_root=runtime_root,
        manifest=manifest,
        company_rows=rows.get("company_info", []),
    )
    limitations = {
        "qbo_source_reported_not_posted_acp_ledger",
        "payment_does_not_duplicate_revenue",
        "customer_references_do_not_create_customer_master",
        "snapshot_is_not_live_synchronization",
    }
    if state != "complete":
        limitations.add("source_acquisition_incomplete")
    if truncated:
        limitations.add("response_family_limit_reached_2000")
    if authorization_marker is None:
        limitations.add("current_provider_authorization_unverified_historical_snapshot")
    accounts = [_account(row) for row in rows.get("account", [])]
    invoices = [_invoice(row) for row in rows.get("invoice", [])]
    payments = [_payment(row) for row in rows.get("payment", [])]
    vendors = [_vendor(row) for row in rows.get("vendor", [])]
    bills = [_bill(row) for row in rows.get("bill", [])]
    company_rows = rows.get("company_info", [])
    company = company_rows[0] if company_rows else {}
    entity_counts = _nonnegative_counts(manifest.get("entity_counts", {}))
    page_counts = _page_counts(manifest.get("pages", []))
    catalog_dispositions = _catalog_dispositions(
        manifest.get("catalog_dispositions", [])
    )
    reports, incompatible_report_date = _report_controls(
        root, basis, as_of=_text(snapshot.get("accounting_date_cutoff"))
    )
    if incompatible_report_date:
        limitations.add("incompatible_report_date_excluded")
    return {
        "contract_version": "qbo-accounting-evidence/v1",
        "source": "quickbooks_online",
        "mode": "live" if authorization_marker is not None else "historical",
        "provider_environment": "production",
        "company_identity_sha256": _company_identity_sha256(snapshot, company),
        "company_info_verified_at": (
            authorization_marker.get("company_info_verified_at")
            if authorization_marker is not None
            else None
        ),
        "source_manifest_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "source_company_label": _text(company.get("CompanyName"))
        or "Verified QBO company",
        "source_company_id_masked": _masked(_text(company.get("Id"))),
        "accounting_basis": basis,
        "as_of": snapshot.get("accounting_date_cutoff"),
        "acquired_at": manifest.get("ended_at"),
        "refresh_state": (
            "available"
            if state == "complete" and authorization_marker is not None
            else "partial"
            if state == "partial" and authorization_marker is not None
            else "stale"
        ),
        "provider_authorization": (
            "verified_current" if authorization_marker is not None else "unverified"
        ),
        "evidence_mode": (
            "current_authorized_snapshot"
            if authorization_marker is not None
            else "historical_snapshot"
        ),
        "completeness": state,
        "entity_counts": entity_counts,
        "page_counts": page_counts,
        "catalog_dispositions": catalog_dispositions,
        "conflicts": [],
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_digest": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "is_live": False,
        "limitations": sorted(limitations),
        "accounts": accounts,
        "invoices": invoices,
        "ar": {
            "total_open": _sum_amounts(invoices, "open_balance"),
            "current": _amount(None, None),
            "overdue": _amount(None, None),
        },
        "payments": payments,
        "vendors": vendors,
        "bills": bills,
        "reports": reports,
        "mutation_authority": "none",
    }


def _verify_current_authorization(
    *,
    runtime_root: Path | None,
    manifest: Mapping[str, object],
    company_rows: list[dict[str, object]],
) -> Mapping[str, object] | None:
    if runtime_root is None:
        return None
    marker_path = runtime_root.expanduser().resolve() / "connections" / "verified.json"
    if not marker_path.is_file():
        return None
    marker = _read_json(marker_path)
    snapshot = manifest.get("snapshot")
    company = company_rows[0] if company_rows else None
    expected = (
        marker.get("environment") == "production",
        marker.get("acquisition_eligible") is True,
        isinstance(snapshot, Mapping),
        isinstance(company, Mapping),
    )
    if not all(expected):
        raise QboEvidenceProjectionError("production_authorization_invalid")
    assert isinstance(snapshot, Mapping)
    assert isinstance(company, Mapping)
    if (
        marker.get("realm_id") != snapshot.get("realm_id")
        or marker.get("company_name") != manifest.get("company_name")
        or marker.get("company_name") != company.get("CompanyName")
        or marker.get("company_info_id") != company.get("Id")
        or marker.get("api_minor_version") != snapshot.get("api_minor_version")
    ):
        raise QboEvidenceProjectionError("production_authorization_conflict")
    return marker


def _company_identity_sha256(
    snapshot: Mapping[str, object], company: Mapping[str, object]
) -> str:
    canonical = {
        "environment": snapshot.get("environment"),
        "realm_id": snapshot.get("realm_id"),
        "company_info_id": company.get("Id"),
        "company_name": company.get("CompanyName"),
    }
    if not all(isinstance(value, str) and value for value in canonical.values()):
        raise QboEvidenceProjectionError("production_company_identity_incomplete")
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _nonnegative_counts(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise QboEvidenceProjectionError("manifest_entity_counts_invalid")
    counts = {str(kind): int(str(count)) for kind, count in value.items()}
    if any(count < 0 for count in counts.values()):
        raise QboEvidenceProjectionError("manifest_entity_counts_invalid")
    return dict(sorted(counts.items()))


def _page_counts(value: object) -> dict[str, int]:
    if not isinstance(value, list):
        raise QboEvidenceProjectionError("manifest_pages_invalid")
    counts: dict[str, int] = {}
    for page in value:
        if not isinstance(page, Mapping):
            raise QboEvidenceProjectionError("manifest_page_invalid")
        kind = _text(page.get("entity_kind"))
        if not kind:
            raise QboEvidenceProjectionError("manifest_page_invalid")
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _catalog_dispositions(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise QboEvidenceProjectionError("manifest_catalog_invalid")
    keys = (
        "entity_kind",
        "requirement",
        "disposition",
        "provider_status_classification",
        "error_classification",
        "observed_at",
    )
    result = []
    for item in value:
        if not isinstance(item, Mapping):
            raise QboEvidenceProjectionError("manifest_catalog_invalid")
        result.append({key: str(item[key]) for key in keys if key in item})
    return sorted(result, key=lambda item: item.get("entity_kind", ""))


def _account(row: Mapping[str, object]) -> dict[str, object]:
    currency = _currency(row)
    return {
        "source_id": _required_id(row),
        "name": _text(row.get("Name")) or "Unnamed source account",
        "account_type": _text(row.get("AccountType")) or "unclassified",
        "account_subtype": _text(row.get("AccountSubType")),
        "balance": _amount(row.get("CurrentBalance"), currency),
    }


def _invoice(row: Mapping[str, object]) -> dict[str, object]:
    currency = _currency(row)
    return {
        "source_id": _required_id(row),
        "document_number": _text(row.get("DocNumber")),
        "customer_label": _ref_name(row.get("CustomerRef")),
        "transaction_date": _text(row.get("TxnDate")),
        "due_date": _text(row.get("DueDate")),
        "source_status": _source_status(row),
        "total": _amount(row.get("TotalAmt"), currency),
        "open_balance": _amount(row.get("Balance"), currency),
    }


def _payment(row: Mapping[str, object]) -> dict[str, object]:
    links = _linked_transactions(row)
    return {
        "source_id": _required_id(row),
        "transaction_date": _text(row.get("TxnDate")),
        "customer_label": _ref_name(row.get("CustomerRef")),
        "source_status": _source_status(row),
        "amount": _amount(row.get("TotalAmt"), _currency(row)),
        "application_state": "source_links_available" if links else "unavailable",
        "applied_document_ids": links,
    }


def _vendor(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "source_id": _required_id(row),
        "display_name": _text(row.get("DisplayName")),
        "active": row.get("Active") if isinstance(row.get("Active"), bool) else None,
        "source_evidence_only": True,
    }


def _bill(row: Mapping[str, object]) -> dict[str, object]:
    currency = _currency(row)
    return {
        "source_id": _required_id(row),
        "document_number": _text(row.get("DocNumber")),
        "vendor_label": _ref_name(row.get("VendorRef")),
        "transaction_date": _text(row.get("TxnDate")),
        "due_date": _text(row.get("DueDate")),
        "source_status": _source_status(row),
        "total": _amount(row.get("TotalAmt"), currency),
        "open_balance": _amount(row.get("Balance"), currency),
    }


def _report_controls(
    root: Path, basis: Basis, *, as_of: str | None
) -> tuple[list[dict[str, object]], bool]:
    reports = []
    incompatible_date = False
    for path in sorted((root / "controls").glob("*.json")):
        control = _read_json(path)
        control_basis = str(control.get("accounting_basis", "")).lower()
        if control.get("schema_version") != "qbo-control-registration/v1":
            continue
        if control_basis == basis and control.get("report_end_date") != as_of:
            incompatible_date = True
            continue
        if control_basis == basis:
            reports.append(
                {
                    "report_key": control.get("control_id"),
                    "label": str(control.get("kind", "source_report"))
                    .replace("_", " ")
                    .title(),
                    "basis": control_basis,
                    "as_of": control.get("report_end_date"),
                    "state": "available",
                    "limitation": "registered_source_report_not_posted_acp_ledger",
                }
            )
    return reports, incompatible_date


def _sum_amounts(rows: list[dict[str, object]], field: str) -> dict[str, object]:
    available: list[tuple[Decimal, str | None]] = []
    for row in rows:
        evidence = row.get(field)
        if not isinstance(evidence, Mapping) or evidence.get("amount") is None:
            continue
        available.append(
            (Decimal(str(evidence["amount"])), _text(evidence.get("currency")))
        )
    currencies = {currency for _, currency in available}
    if not available or len(currencies) != 1 or None in currencies:
        return _amount(None, None)
    return _amount(
        sum((amount for amount, _ in available), Decimal(0)),
        str(next(iter(currencies))),
    )


def _amount(value: object, currency: str | None) -> dict[str, object]:
    if value is None:
        return {"amount": None, "currency": currency, "state": "unavailable"}
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise QboEvidenceProjectionError("source_amount_invalid") from error
    if not amount.is_finite():
        raise QboEvidenceProjectionError("source_amount_invalid")
    return {"amount": format(amount, "f"), "currency": currency, "state": "available"}


def _currency(row: Mapping[str, object]) -> str | None:
    value = row.get("CurrencyRef")
    return _text(value.get("value")) if isinstance(value, Mapping) else None


def _ref_name(value: object) -> str | None:
    return _text(value.get("name")) if isinstance(value, Mapping) else None


def _linked_transactions(row: Mapping[str, object]) -> list[str]:
    lines = row.get("Line")
    if not isinstance(lines, list):
        return []
    found = set()
    for line in lines:
        linked = line.get("LinkedTxn") if isinstance(line, Mapping) else None
        for item in linked if isinstance(linked, list) else []:
            identifier = item.get("TxnId") if isinstance(item, Mapping) else None
            if isinstance(identifier, str) and identifier:
                found.add(identifier)
    return sorted(found)


def _source_status(row: Mapping[str, object]) -> str | None:
    return next(
        (
            _text(row.get(key))
            for key in ("TxnStatus", "status", "PrintStatus", "EmailStatus")
            if _text(row.get(key))
        ),
        None,
    )


def _required_id(row: Mapping[str, object]) -> str:
    value = _text(row.get("Id"))
    if not value:
        raise QboEvidenceProjectionError("source_identity_missing")
    return value


def _masked(value: str | None) -> str:
    return f"…{value[-4:]}" if value and len(value) > 4 else "verified"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise QboEvidenceProjectionError("protected_evidence_unreadable") from error
    if not isinstance(value, dict):
        raise QboEvidenceProjectionError("protected_evidence_invalid")
    return value
