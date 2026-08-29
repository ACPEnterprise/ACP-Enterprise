from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from .contracts import QboSourceEnvelope

TRANSFORMATION_VERSION = "qbo-source-transformation/v1"


@dataclass(frozen=True)
class QboTransformationCandidate:
    transformation_version: str
    native_entity_type: str
    native_id: str
    raw_sha256: str
    source_status: str | None
    currency: str | None
    relationship_ids: tuple[str, ...]
    source_fields: Mapping[str, object]
    candidate_kind: str
    accounting_acceptance: str
    candidate_sha256: str

    def __post_init__(self) -> None:
        if self.accounting_acceptance != "source_evidence_only_unreconciled":
            raise ValueError("QBO transformation cannot promote Accounting truth")
        object.__setattr__(
            self, "source_fields", MappingProxyType(dict(self.source_fields))
        )


_CANDIDATE_KINDS = {
    "account": "account_reference_candidate",
    "customer": "customer_reference_candidate",
    "vendor": "vendor_reference_candidate",
    "item": "item_reference_candidate",
    "invoice": "ar_invoice_evidence_candidate",
    "payment": "payment_application_evidence_candidate",
    "bill": "ap_bill_evidence_candidate",
    "bill_payment": "bill_payment_evidence_candidate",
    "purchase": "cash_purchase_evidence_candidate",
    "credit_memo": "customer_credit_evidence_candidate",
    "vendor_credit": "vendor_credit_evidence_candidate",
    "deposit": "deposit_evidence_candidate",
    "journal_entry": "journal_evidence_candidate",
    "transfer": "transfer_evidence_candidate",
    "term": "term_reference_candidate",
    "payment_method": "payment_method_reference_candidate",
    "class": "class_reference_candidate",
    "department": "department_reference_candidate",
}


def transform_qbo_envelope(envelope: QboSourceEnvelope) -> QboTransformationCandidate:
    source_fields = _source_fields(envelope)
    canonical = {
        "transformation_version": TRANSFORMATION_VERSION,
        "native_entity_type": envelope.native_entity_type,
        "native_id": envelope.native_id,
        "raw_sha256": envelope.raw_sha256,
        "source_status": envelope.source_status,
        "currency": envelope.currency,
        "relationship_ids": list(envelope.relationship_ids),
        "source_fields": source_fields,
        "candidate_kind": _CANDIDATE_KINDS.get(
            envelope.native_entity_type, "source_context_candidate"
        ),
        "accounting_acceptance": "source_evidence_only_unreconciled",
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return QboTransformationCandidate(
        transformation_version=TRANSFORMATION_VERSION,
        native_entity_type=envelope.native_entity_type,
        native_id=envelope.native_id,
        raw_sha256=envelope.raw_sha256,
        source_status=envelope.source_status,
        currency=envelope.currency,
        relationship_ids=tuple(envelope.relationship_ids),
        source_fields=source_fields,
        candidate_kind=str(canonical["candidate_kind"]),
        accounting_acceptance="source_evidence_only_unreconciled",
        candidate_sha256=digest,
    )


def _source_fields(envelope: QboSourceEnvelope) -> dict[str, object]:
    raw = envelope.raw_payload
    fields: dict[str, object] = {
        "source_accounting_meaning": dict(envelope.source_accounting_meaning)
    }
    for key in (
        "Name",
        "DisplayName",
        "Active",
        "TxnDate",
        "DueDate",
        "DocNumber",
        "PaymentRefNum",
        "PaymentType",
        "AccountType",
        "AccountSubType",
    ):
        if key in raw:
            fields[key] = raw[key]
    for key in ("TotalAmt", "Balance", "RemainingCredit", "Amount"):
        if key in raw:
            fields[key] = _decimal_string(raw[key], key)
    lines = raw.get("Line")
    if isinstance(lines, tuple):
        fields["line_count"] = len(lines)
        fields["line_amount_total"] = format(
            sum(
                (
                    Decimal(_decimal_string(line.get("Amount"), "line_amount"))
                    for line in lines
                    if isinstance(line, Mapping) and line.get("Amount") is not None
                ),
                Decimal(0),
            ),
            "f",
        )
    return fields


def _decimal_string(value: object, field: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise TypeError(f"{field} must be a source decimal")
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{field} must be a source decimal") from error
    if not decimal.is_finite():
        raise ValueError(f"{field} must be finite")
    return format(decimal, "f")
