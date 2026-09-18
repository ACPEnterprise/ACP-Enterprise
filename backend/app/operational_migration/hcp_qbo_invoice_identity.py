"""Exact-only HCP/QBO Invoice identity and parent-readiness inventory.

QBO control-report rows are source evidence, not QBO entity exports.  Document
numbers, dates, names, and amounts are retained as supporting evidence but can
never establish an identity by themselves.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final
from zipfile import ZipFile

from app.qbo_source.ledger_opening_analysis import _shared_strings, _sheet_rows

CONTRACT: Final = "hcp-qbo-invoice-identity-inventory/v1"
_HCP_INVOICE_REFERENCE = re.compile(
    r"(?<![A-Za-z0-9_])(invoice_[0-9a-f]{32})(?![A-Za-z0-9_])"
)


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _collection(source_root: Path, name: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((source_root / "raw" / name).glob("page-*.json")):
        value = json.loads(path.read_bytes())
        records.extend(value[name])
    return records


@dataclass(frozen=True)
class InvoiceIdentityInventory:
    contract: str
    hcp_manifest_sha256: str
    qbo_registration_sha256: str
    qbo_raw_sha256: str
    counts: dict[str, int]
    hcp_records: tuple[dict[str, object], ...]
    qbo_records: tuple[dict[str, object], ...]
    authority: dict[str, object]
    digest: str

    def verify(self) -> None:
        value = asdict(self)
        expected = value.pop("digest")
        if self.contract != CONTRACT or _digest(value) != expected:
            raise ValueError("invoice identity inventory digest mismatch")


def build_invoice_identity_inventory(
    *, hcp_source_root: Path, qbo_registration_path: Path, qbo_raw_path: Path
) -> InvoiceIdentityInventory:
    """Inventory exact identities without matching on weak report attributes."""
    manifest_path = hcp_source_root / "acquisition-package-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract") != "hcp-source-4-acquisition-package/v1":
        raise ValueError("unsupported HCP source package")
    if manifest.get("request_methods") != ["GET"]:
        raise ValueError("HCP source package is not read-only")

    registration_bytes = qbo_registration_path.read_bytes()
    registration = json.loads(registration_bytes)
    if registration.get("schema_version") != "qbo-control-registration/v1":
        raise ValueError("unsupported QBO control registration")
    raw_bytes = qbo_raw_path.read_bytes()
    qbo_raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if registration.get("raw_sha256") != qbo_raw_sha256:
        raise ValueError("QBO control raw digest mismatch")
    if registration.get("byte_size") != len(raw_bytes):
        raise ValueError("QBO control raw byte size mismatch")

    jobs = _collection(hcp_source_root, "jobs")
    invoices = _collection(hcp_source_root, "invoices")
    job_by_id = {str(job["id"]): job for job in jobs}
    if len(job_by_id) != len(jobs):
        raise ValueError("duplicate HCP Job identity")
    invoice_ids = [str(invoice["id"]) for invoice in invoices]
    if len(set(invoice_ids)) != len(invoice_ids):
        raise ValueError("duplicate HCP Invoice identity")

    hcp_records: list[dict[str, object]] = []
    for invoice in sorted(invoices, key=lambda item: str(item["id"])):
        job_id = str(invoice.get("job_id") or "")
        job = job_by_id.get(job_id)
        customer_id = ""
        address_id = ""
        if job is not None:
            customer = job.get("customer") or {}
            address = job.get("address") or {}
            customer_id = str(customer.get("id") or "")
            address_id = str(address.get("id") or "")
        hcp_records.append(
            {
                "hcp_invoice_id": str(invoice["id"]),
                "invoice_number": str(invoice.get("invoice_number") or ""),
                "job_id": job_id,
                "customer_id": customer_id or None,
                "location_source_id": address_id or None,
                "status": invoice.get("status"),
                "service_date": invoice.get("service_date"),
                "invoice_date": invoice.get("invoice_date"),
                "amount_minor": invoice.get("amount"),
                "balance_minor": invoice.get("due_amount"),
                "parent_disposition": (
                    "EXACT_SOURCE_JOB_PARENT"
                    if job is not None
                    else "SOURCE_JOB_PARENT_MISSING"
                ),
                "alternate_history_disposition": (
                    "CUSTOMER_HISTORY_EXACT"
                    if customer_id
                    else "LEGACY_ONLY_SOURCE_INVOICE_NO_AUTHORITATIVE_CUSTOMER"
                ),
                "identity_disposition": "NO_EXACT_BINDING",
                "source_digest": _digest(invoice),
            }
        )

    qbo_records = _qbo_invoice_rows(qbo_raw_path, set(invoice_ids))
    exact_references = Counter(str(row["identity_disposition"]) for row in qbo_records)
    parent_counts = Counter(str(row["parent_disposition"]) for row in hcp_records)
    counts = {
        "hcp_invoice_count": len(hcp_records),
        "hcp_exact_source_job_parent": parent_counts["EXACT_SOURCE_JOB_PARENT"],
        "hcp_source_job_parent_missing": parent_counts["SOURCE_JOB_PARENT_MISSING"],
        "hcp_missing_parent_customer_history_exact": sum(
            row["parent_disposition"] == "SOURCE_JOB_PARENT_MISSING"
            and row["alternate_history_disposition"] == "CUSTOMER_HISTORY_EXACT"
            for row in hcp_records
        ),
        "hcp_missing_parent_legacy_only": sum(
            row["alternate_history_disposition"]
            == "LEGACY_ONLY_SOURCE_INVOICE_NO_AUTHORITATIVE_CUSTOMER"
            for row in hcp_records
        ),
        "qbo_invoice_control_row_count": len(qbo_records),
        "exact_provider_reference": exact_references["EXACT_PROVIDER_REFERENCE"],
        "no_exact_binding": exact_references["NO_EXACT_BINDING"],
        "conflicting_binding": exact_references["CONFLICTING_BINDING"],
    }
    authority: dict[str, object] = {
        "classification": "SOURCE_EVIDENCE_ONLY",
        "aggregation_safe": False,
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "prohibited_identity_evidence": [
            "document_number_alone",
            "amount_alone",
            "date_alone",
            "customer_name_alone",
            "any_combination_without_explicit_provider_reference",
        ],
    }
    payload = {
        "contract": CONTRACT,
        "hcp_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "qbo_registration_sha256": hashlib.sha256(registration_bytes).hexdigest(),
        "qbo_raw_sha256": qbo_raw_sha256,
        "counts": counts,
        "hcp_records": tuple(hcp_records),
        "qbo_records": tuple(qbo_records),
        "authority": authority,
    }
    return InvoiceIdentityInventory(
        contract=CONTRACT,
        hcp_manifest_sha256=str(payload["hcp_manifest_sha256"]),
        qbo_registration_sha256=str(payload["qbo_registration_sha256"]),
        qbo_raw_sha256=qbo_raw_sha256,
        counts=counts,
        hcp_records=tuple(hcp_records),
        qbo_records=tuple(qbo_records),
        authority=authority,
        digest=_digest(payload),
    )


def _qbo_invoice_rows(path: Path, hcp_invoice_ids: set[str]) -> list[dict[str, object]]:
    with ZipFile(path) as workbook:
        rows = _sheet_rows(workbook, _shared_strings(workbook))
    header = next((row for row in rows if "Transaction type" in row.values()), None)
    if header is None:
        raise ValueError("QBO transaction header missing")
    columns = {value: column for column, value in header.items()}
    required = ("Transaction date", "Transaction type", "Num", "Name", "Amount")
    if any(name not in columns for name in required):
        raise ValueError("QBO transaction columns missing")

    result: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        if row.get(columns["Transaction type"]) != "Invoice":
            continue
        evidence_text = " ".join(str(value) for value in row.values())
        references = sorted(set(_HCP_INVOICE_REFERENCE.findall(evidence_text)))
        known = [reference for reference in references if reference in hcp_invoice_ids]
        if len(known) == 1 and len(references) == 1:
            disposition = "EXACT_PROVIDER_REFERENCE"
        elif len(known) > 1 or len(references) > 1:
            disposition = "CONFLICTING_BINDING"
        else:
            disposition = "NO_EXACT_BINDING"
        result.append(
            {
                "control_row": index,
                "transaction_date": row.get(columns["Transaction date"], ""),
                "transaction_type": "Invoice",
                "document_number": row.get(columns["Num"], ""),
                "customer_name_supporting_only": row.get(columns["Name"], ""),
                "amount_supporting_only": row.get(columns["Amount"], ""),
                "explicit_hcp_invoice_references": references,
                "identity_disposition": disposition,
                "row_digest": _digest(row),
            }
        )
    return result


def classify_payment_control_invoice_links(
    *, control_root: Path, hcp_source_root: Path
) -> dict[str, object]:
    """Classify every HCP control-export row without elevating Invoice Number.

    The private export contains Job/Customer control IDs and an Invoice Number,
    but not the public API Invoice provider identity.  Consequently these rows
    remain ``NO_BINDING_EVIDENCE`` even if a document number happens to be
    unique.  That is intentional: document numbers are supporting evidence.
    """
    manifest_path = control_root / "hcp-control-manifest-v1.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("contract_version") != "hcp-controls-intake/1":
        raise ValueError("unsupported HCP control manifest")
    invoices = _collection(hcp_source_root, "invoices")
    invoice_numbers = Counter(
        str(item.get("invoice_number") or "") for item in invoices
    )
    rows: list[dict[str, object]] = []
    for entry in manifest.get("entries", []):
        if entry.get("classification") != "PAYMENTS_DETAIL":
            continue
        path = control_root / str(entry["protected_reference"])
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry.get("sha256"):
            raise ValueError("HCP control digest mismatch")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        artifact_rows = list(reader)
        if len(artifact_rows) != entry.get("row_count"):
            raise ValueError("HCP control row count mismatch")
        for row_number, row in enumerate(artifact_rows, start=2):
            invoice_number = str(row.get("Invoice Number") or "")
            rows.append(
                {
                    "control_sha256": entry["sha256"],
                    "control_row": row_number,
                    "private_job_id": row.get("Job ID") or None,
                    "private_customer_id": row.get("Customer ID") or None,
                    "invoice_number_supporting_only": invoice_number or None,
                    "invoice_number_api_candidate_count": invoice_numbers[
                        invoice_number
                    ],
                    "payment_type": row.get("Payment Type") or None,
                    "disposition": "NO_BINDING_EVIDENCE",
                    "reason": "control_row_has_no_public_api_invoice_provider_identity",
                    "row_digest": _digest(row),
                }
            )
    return {
        "contract": "hcp-control-invoice-linkage/v1",
        "control_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "record_count": len(rows),
        "counts": {
            "EXACT_LINK": 0,
            "MULTIPLE_EXACT_CANDIDATES": 0,
            "NO_BINDING_EVIDENCE": len(rows),
            "CONFLICTING": 0,
            "NOT_INVOICE_RELATED": 0,
        },
        "records": rows,
        "mutation_authority": "none",
        "aggregation_safe": False,
        "digest": _digest(rows),
    }
