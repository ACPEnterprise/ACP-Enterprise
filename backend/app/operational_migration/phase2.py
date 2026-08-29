"""Deterministic Housecall Pro financial-history migration contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.operational_migration.financial import (
    FinancialLineItemRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.phase1 import ReviewedOperationalOutput

SOURCE_SYSTEM = "housecall_pro"
EXPORT_VERSION = "housecall_pro_job_export_20240321_v1"
REVIEW_VERSION = "operational-migration-phase2-review/v1"
MANIFEST_VERSION = "operational-migration-phase2-manifest/v1"
SELECTION_VERSION = "source-identity-sha256/v1"
TRANSFORMATION_VERSION = "operational-phase2-hcp-financial/v1"

_MONEY = re.compile(r"^\$([0-9,]+(?:\.\d+)?)$")
_LINE_ITEM = re.compile(r"^(.*?) - \$([0-9,]+(?:\.\d+)?)$")
_PAYMENT = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}(?:am|pm)) - "
    r"(\(?\$[0-9,]+(?:\.\d+)?\)?) - (.*?) - "
    r"(?=\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}(?:am|pm)|$)",
    re.IGNORECASE,
)


def _canonical(value: object) -> str:
    def encode(item: object) -> str:
        if isinstance(item, datetime):
            return item.isoformat()
        return str(item)

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode)


def _sha256(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def _amount(value: str) -> Decimal:
    match = _MONEY.fullmatch(value.strip())
    if not match:
        raise ValueError("source monetary value is not canonical")
    try:
        amount = Decimal(match.group(1).replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise ValueError("source monetary value is invalid") from error
    if amount < 0:
        raise ValueError("source monetary value is negative")
    return amount


def _payment_amount(value: str) -> Decimal:
    negative = value.startswith("(") and value.endswith(")")
    amount = _amount(value[1:-1] if negative else value)
    return -amount if negative else amount


def _timestamp(value: str) -> datetime:
    return datetime.strptime(value.lower(), "%Y-%m-%d %I:%M%p").replace(
        tzinfo=ZoneInfo("America/New_York")
    )


@dataclass(frozen=True)
class FinancialDisposition:
    entity_type: Literal["invoice", "payment"]
    row_number: int
    source_id_sha256: str | None
    category: str


@dataclass(frozen=True)
class Phase2Review:
    source_sha256: str
    phase1_review_sha256: str
    transformation_sha256: str
    invoices: tuple[InvoiceMigrationRecord, ...]
    payments: tuple[PaymentMigrationRecord, ...]
    dispositions: tuple[FinancialDisposition, ...]
    source_count: int

    def payload(self) -> dict[str, object]:
        return {
            "review_version": REVIEW_VERSION,
            "source_system": SOURCE_SYSTEM,
            "export_version": EXPORT_VERSION,
            "transformation_version": TRANSFORMATION_VERSION,
            "source_sha256": self.source_sha256,
            "phase1_review_sha256": self.phase1_review_sha256,
            "transformation_sha256": self.transformation_sha256,
            "source_count": self.source_count,
            "eligible_estimate_count": 0,
            "eligible_estimate_line_item_count": 0,
            "eligible_invoice_count": len(self.invoices),
            "eligible_invoice_line_item_count": sum(
                len(item.line_items) for item in self.invoices
            ),
            "eligible_payment_count": len(self.payments),
            "invoices": [asdict(item) for item in self.invoices],
            "payments": [asdict(item) for item in self.payments],
            "dispositions": [asdict(item) for item in self.dispositions],
            "disposition_counts": dict(
                sorted(Counter(item.category for item in self.dispositions).items())
            ),
        }


class ReviewedFinancialOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_version: Literal["operational-migration-phase2-review/v1"]
    source_system: Literal["housecall_pro"]
    export_version: Literal["housecall_pro_job_export_20240321_v1"]
    transformation_version: Literal["operational-phase2-hcp-financial/v1"]
    source_sha256: str
    phase1_review_sha256: str
    transformation_sha256: str
    source_count: int = Field(ge=0)
    eligible_estimate_count: int = Field(ge=0)
    eligible_estimate_line_item_count: int = Field(ge=0)
    eligible_invoice_count: int = Field(ge=0)
    eligible_invoice_line_item_count: int = Field(ge=0)
    eligible_payment_count: int = Field(ge=0)
    invoices: tuple[dict[str, Any], ...]
    payments: tuple[dict[str, Any], ...]
    dispositions: tuple[dict[str, Any], ...]
    disposition_counts: dict[str, int]
    review_sha256: str

    @model_validator(mode="after")
    def validate_integrity(self) -> ReviewedFinancialOutput:
        if self.eligible_estimate_count or self.eligible_estimate_line_item_count:
            raise ValueError("source export does not contain Estimate records")
        if self.eligible_invoice_count != len(self.invoices):
            raise ValueError("eligible Invoice count does not reconcile")
        if self.eligible_payment_count != len(self.payments):
            raise ValueError("eligible Payment count does not reconcile")
        if self.source_count != self.eligible_invoice_count + len(
            [item for item in self.dispositions if item["entity_type"] == "invoice"]
        ):
            raise ValueError("source Invoice count does not reconcile")
        expected = _sha256(
            _canonical(self.model_dump(exclude={"review_sha256"}, mode="json"))
        )
        if expected != self.review_sha256:
            raise ValueError("reviewed financial output digest mismatch")
        return self

    def invoice_records(self) -> tuple[InvoiceMigrationRecord, ...]:
        result = []
        for value in self.invoices:
            payload = dict(value)
            payload["subtotal_amount"] = Decimal(payload["subtotal_amount"])
            payload["tax_amount"] = Decimal(payload["tax_amount"])
            payload["total_amount"] = Decimal(payload["total_amount"])
            payload["line_items"] = tuple(
                FinancialLineItemRecord(
                    source_id=item["source_id"],
                    description=item["description"],
                    quantity=Decimal(item["quantity"]),
                    unit_price=Decimal(item["unit_price"]),
                    total_amount=Decimal(item["total_amount"]),
                )
                for item in payload["line_items"]
            )
            result.append(InvoiceMigrationRecord(**payload))
        return tuple(result)

    def payment_records(self) -> tuple[PaymentMigrationRecord, ...]:
        result = []
        for value in self.payments:
            payload = dict(value)
            payload["amount"] = Decimal(payload["amount"])
            if isinstance(payload.get("paid_at"), str):
                payload["paid_at"] = datetime.fromisoformat(payload["paid_at"])
            result.append(PaymentMigrationRecord(**payload))
        return tuple(result)


class OperationalPhase2Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal["operational-migration-phase2-manifest/v1"]
    selection_version: Literal["source-identity-sha256/v1"]
    stage_identifier: str
    prior_stage_identifier: str | None
    prior_stage_manifest_sha256: str | None
    source_system: Literal["housecall_pro"]
    source_sha256: str
    export_version: Literal["housecall_pro_job_export_20240321_v1"]
    transformation_version: Literal["operational-phase2-hcp-financial/v1"]
    transformation_sha256: str
    reviewed_output_sha256: str
    phase1_review_sha256: str
    ordered_invoice_source_identities: tuple[str, ...]
    ordered_invoice_identity_sha256: tuple[str, ...]
    ordered_payment_source_identities: tuple[str, ...]
    expected_estimates: int = Field(ge=0)
    expected_estimate_line_items: int = Field(ge=0)
    expected_invoices: int = Field(ge=0)
    expected_invoice_line_items: int = Field(ge=0)
    expected_payments: int = Field(ge=0)
    expected_business_events: int = Field(ge=0)
    eligibility: dict[str, int]
    replay_digest: str
    generated_at: datetime
    manifest_sha256: str

    @model_validator(mode="after")
    def validate_integrity(self) -> OperationalPhase2Manifest:
        if self.expected_invoices != len(self.ordered_invoice_source_identities):
            raise ValueError("manifest Invoice count does not reconcile")
        if self.expected_payments != len(self.ordered_payment_source_identities):
            raise ValueError("manifest Payment count does not reconcile")
        if tuple(map(_sha256, self.ordered_invoice_source_identities)) != (
            self.ordered_invoice_identity_sha256
        ):
            raise ValueError("manifest identity digests do not reconcile")
        expected = _sha256(
            _canonical(self.model_dump(exclude={"manifest_sha256"}, mode="json"))
        )
        if expected != self.manifest_sha256:
            raise ValueError("operational financial manifest digest mismatch")
        return self


def _line_items(
    value: str, source_invoice_id: str
) -> tuple[FinancialLineItemRecord, ...]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("incomplete_financial_detail")
    result = []
    for position, line in enumerate(lines[1:], start=1):
        match = _LINE_ITEM.fullmatch(line)
        if not match or not match.group(1).strip():
            raise ValueError("incomplete_financial_detail")
        amount = Decimal(match.group(2).replace(",", "")).quantize(Decimal("0.01"))
        result.append(
            FinancialLineItemRecord(
                source_id=f"{source_invoice_id}::line::{position}",
                description=match.group(1).strip(),
                quantity=Decimal("1.000"),
                unit_price=amount,
                total_amount=amount,
            )
        )
    return tuple(result)


def _payments(value: str, source_invoice_id: str) -> tuple[PaymentMigrationRecord, ...]:
    if not value:
        return ()
    matches = tuple(_PAYMENT.finditer(value))
    if not matches or "".join(item.group(0) for item in matches) != value:
        raise ValueError("incomplete_financial_detail")
    result = []
    for position, match in enumerate(matches, start=1):
        amount = _payment_amount(match.group(2))
        method = match.group(3).strip() or None
        if amount <= 0 or method == "Credit Card Refund":
            raise ValueError("unsupported_lifecycle")
        result.append(
            PaymentMigrationRecord(
                source_id=f"{source_invoice_id}::payment::{position}",
                source_invoice_id=source_invoice_id,
                status="succeeded",
                currency="USD",
                amount=amount,
                paid_at=_timestamp(match.group(1)),
                method=method,
                external_metadata={"source_status": "historical_payment"},
            )
        )
    return tuple(result)


def transform_phase2(
    *, source_bytes: bytes, phase1_review_bytes: bytes
) -> Phase2Review:
    phase1 = ReviewedOperationalOutput.model_validate_json(phase1_review_bytes)
    if _sha256(source_bytes) != phase1.source_sha256:
        raise ValueError("financial source does not match accepted Phase 1 source")
    rows = list(csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig"))))
    imported_jobs = {item.source_id for item in phase1.job_records()}
    invoices: list[InvoiceMigrationRecord] = []
    payments: list[PaymentMigrationRecord] = []
    dispositions: list[FinancialDisposition] = []
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=2):
        job_id = row["HCP Id"].strip()
        invoice_id = row["Invoice"].strip()
        source_digest = _sha256(invoice_id) if invoice_id else None
        category = None
        if job_id not in imported_jobs:
            category = "unresolved_job"
        elif not invoice_id:
            category = "unresolved_invoice"
        elif invoice_id in seen:
            category = "duplicate_source_identity"
        else:
            seen.add(invoice_id)
            try:
                subtotal = _amount(row["Subtotal"])
                total = _amount(row["Amount"])
                items = _line_items(row["Line Items"], invoice_id)
                row_payments = _payments(row["Payment History"], invoice_id)
                if (
                    sum((item.total_amount for item in items), Decimal(0)) != subtotal
                    or total != subtotal
                    or row_payments
                    and sum((item.amount for item in row_payments), Decimal(0)) != total
                ):
                    category = "monetary_imbalance"
            except ValueError as error:
                category = str(error)
        if category:
            dispositions.append(
                FinancialDisposition("invoice", row_number, source_digest, category)
            )
            continue
        invoices.append(
            InvoiceMigrationRecord(
                source_id=invoice_id,
                source_job_id=job_id,
                status="draft",
                currency="USD",
                subtotal_amount=subtotal,
                tax_amount=Decimal("0.00"),
                total_amount=total,
                line_items=items,
                external_metadata={
                    "source_job_status": row["Job Status"],
                    "source_invoice_number": invoice_id,
                    "source_lifecycle_status": "not_exported",
                },
            )
        )
        payments.extend(row_payments)
    invoices.sort(key=lambda item: (_sha256(item.source_id), item.source_id))
    payment_parent_order = {
        item.source_id: index for index, item in enumerate(invoices)
    }
    payments.sort(
        key=lambda item: (payment_parent_order[item.source_invoice_id], item.source_id)
    )
    transform_payload = {
        "version": TRANSFORMATION_VERSION,
        "source": phase1.source_sha256,
        "phase1_review": phase1.review_sha256,
        "invoices": [asdict(item) for item in invoices],
        "payments": [asdict(item) for item in payments],
        "dispositions": [asdict(item) for item in dispositions],
    }
    return Phase2Review(
        source_sha256=phase1.source_sha256,
        phase1_review_sha256=phase1.review_sha256,
        transformation_sha256=_sha256(_canonical(transform_payload)),
        invoices=tuple(invoices),
        payments=tuple(payments),
        dispositions=tuple(dispositions),
        source_count=len(rows),
    )


def reviewed_output(review: Phase2Review) -> ReviewedFinancialOutput:
    payload = review.payload()
    payload["review_sha256"] = _sha256(_canonical(payload))
    return ReviewedFinancialOutput.model_validate(payload)


def select_stage(
    reviewed: ReviewedFinancialOutput,
    *,
    stage_identifier: str,
    limit: int | None,
    prior: OperationalPhase2Manifest | None,
    generated_at: datetime,
) -> OperationalPhase2Manifest:
    invoices = reviewed.invoice_records()
    selected = invoices if limit is None else invoices[:limit]
    invoice_ids = tuple(item.source_id for item in selected)
    if (
        prior
        and invoice_ids[: prior.expected_invoices]
        != prior.ordered_invoice_source_identities
    ):
        raise ValueError("stage is not a cumulative extension of its prior stage")
    selected_set = set(invoice_ids)
    payments = tuple(
        item
        for item in reviewed.payment_records()
        if item.source_invoice_id in selected_set
    )
    line_item_count = sum(len(item.line_items) for item in selected)
    replay = _sha256(
        _canonical(
            {
                "source_system": SOURCE_SYSTEM,
                "estimates": [],
                "invoices": [asdict(item) for item in selected],
                "payments": [asdict(item) for item in payments],
            }
        )
    )
    payload: dict[str, object] = {
        "manifest_version": MANIFEST_VERSION,
        "selection_version": SELECTION_VERSION,
        "stage_identifier": stage_identifier,
        "prior_stage_identifier": prior.stage_identifier if prior else None,
        "prior_stage_manifest_sha256": prior.manifest_sha256 if prior else None,
        "source_system": SOURCE_SYSTEM,
        "source_sha256": reviewed.source_sha256,
        "export_version": EXPORT_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "transformation_sha256": reviewed.transformation_sha256,
        "reviewed_output_sha256": reviewed.review_sha256,
        "phase1_review_sha256": reviewed.phase1_review_sha256,
        "ordered_invoice_source_identities": invoice_ids,
        "ordered_invoice_identity_sha256": tuple(map(_sha256, invoice_ids)),
        "ordered_payment_source_identities": tuple(item.source_id for item in payments),
        "expected_estimates": 0,
        "expected_estimate_line_items": 0,
        "expected_invoices": len(selected),
        "expected_invoice_line_items": line_item_count,
        "expected_payments": len(payments),
        "expected_business_events": len(selected) + len(payments),
        "eligibility": {
            "source": reviewed.source_count,
            "eligible_estimates": reviewed.eligible_estimate_count,
            "eligible_invoices": reviewed.eligible_invoice_count,
            "eligible_payments": reviewed.eligible_payment_count,
            **reviewed.disposition_counts,
        },
        "replay_digest": replay,
        "generated_at": generated_at,
    }
    payload["manifest_sha256"] = "0" * 64
    provisional = OperationalPhase2Manifest.model_construct(
        _fields_set=None, **payload
    )
    payload["manifest_sha256"] = _sha256(
        _canonical(provisional.model_dump(exclude={"manifest_sha256"}, mode="json"))
    )
    return OperationalPhase2Manifest.model_validate(payload)


def stage_records(
    reviewed: ReviewedFinancialOutput, manifest: OperationalPhase2Manifest
) -> tuple[tuple[InvoiceMigrationRecord, ...], tuple[PaymentMigrationRecord, ...]]:
    if (
        reviewed.review_sha256 != manifest.reviewed_output_sha256
        or reviewed.source_sha256 != manifest.source_sha256
        or reviewed.transformation_sha256 != manifest.transformation_sha256
    ):
        raise ValueError("reviewed output does not match financial manifest")
    invoice_map = {item.source_id: item for item in reviewed.invoice_records()}
    payment_map = {item.source_id: item for item in reviewed.payment_records()}
    invoices = tuple(
        invoice_map[item] for item in manifest.ordered_invoice_source_identities
    )
    payments = tuple(
        payment_map[item] for item in manifest.ordered_payment_source_identities
    )
    digest = _sha256(
        _canonical(
            {
                "source_system": SOURCE_SYSTEM,
                "estimates": [],
                "invoices": [asdict(item) for item in invoices],
                "payments": [asdict(item) for item in payments],
            }
        )
    )
    if digest != manifest.replay_digest:
        raise ValueError("financial stage replay digest mismatch")
    return invoices, payments
