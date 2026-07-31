import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.economics.contracts import EvidenceInput, RecordBusinessFact
from app.economics.domain import (
    Confidence,
    EconomicCategory,
    EvidenceKind,
    MeasurementStatus,
)
from app.events.models import BusinessEvent


class IdentifiedSource(Protocol):
    id: UUID


class InvoiceSource(IdentifiedSource, Protocol):
    company_id: UUID
    branch_id: UUID
    job_id: UUID
    status: str
    currency: str
    total_amount: Decimal
    issued_at: datetime | None
    created_at: datetime


class PaymentSource(IdentifiedSource, Protocol):
    company_id: UUID
    branch_id: UUID
    invoice_id: UUID
    status: str
    currency: str
    amount: Decimal
    paid_at: datetime | None


class EconomicsSourceAdapterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterContext:
    business_event_id: UUID
    business_event_version: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class AdapterResult:
    commands: tuple[RecordBusinessFact, ...]
    omission_reason: str | None = None


class EconomicsSourceAdapter(Protocol):
    def adapt(self, source: object, context: AdapterContext) -> AdapterResult: ...


@dataclass(frozen=True, slots=True)
class MeasuredOperationalCost:
    id: UUID
    company_id: UUID
    branch_id: UUID
    job_id: UUID
    amount_minor: int
    currency: str
    period_start: date
    period_end: date
    occurred_at: datetime
    source_version: str
    measurement_method: str


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _minor_units(amount: Decimal) -> int:
    minor = amount * 100
    if minor != minor.to_integral_value():
        raise EconomicsSourceAdapterError("source amount has sub-minor-unit precision")
    return int(minor)


def _evidence(
    *,
    context: AdapterContext,
    source_system: str,
    source_record_type: str,
    reference_id: UUID,
    source_version: str,
    content: dict[str, object],
) -> tuple[EvidenceInput, EvidenceInput]:
    digest = _digest(content)
    return (
        EvidenceInput(
            kind=EvidenceKind.SOURCE_RECORD,
            reference_id=str(reference_id),
            source_system=source_system,
            source_record_type=source_record_type,
            source_version=source_version,
            content_digest=digest,
            observed_at=context.observed_at,
            explanation=f"Authoritative {source_record_type} source record.",
        ),
        EvidenceInput(
            kind=EvidenceKind.BUSINESS_EVENT,
            reference_id=str(context.business_event_id),
            source_system="acp_enterprise",
            source_record_type="business_event",
            source_version=context.business_event_version,
            content_digest=_digest(
                {
                    "business_event_id": str(context.business_event_id),
                    "source_digest": digest,
                }
            ),
            observed_at=context.observed_at,
            explanation="Business Event that triggered economics ingestion.",
            business_event_id=context.business_event_id,
        ),
    )


class JobSourceAdapter:
    def adapt(self, source: IdentifiedSource, context: AdapterContext) -> AdapterResult:
        del context
        return AdapterResult(
            commands=(),
            omission_reason=(
                f"Job {source.id} contains no measured monetary economics value."
            ),
        )


class AppointmentSourceAdapter:
    def adapt(self, source: IdentifiedSource, context: AdapterContext) -> AdapterResult:
        del context
        return AdapterResult(
            commands=(),
            omission_reason=(
                f"Appointment {source.id} exposes expected, not measured, duration."
            ),
        )


class InvoiceSourceAdapter:
    def adapt(self, source: InvoiceSource, context: AdapterContext) -> AdapterResult:
        if source.status not in {"issued", "partially_paid", "paid"}:
            return AdapterResult((), f"Invoice {source.id} is not recognized revenue.")
        occurred_at = source.issued_at or source.created_at
        content: dict[str, object] = {
            "id": str(source.id),
            "company_id": str(source.company_id),
            "branch_id": str(source.branch_id),
            "job_id": str(source.job_id),
            "status": source.status,
            "currency": source.currency,
            "total_amount": str(source.total_amount),
            "issued_at": source.issued_at,
        }
        version = f"{source.status}:{occurred_at.isoformat()}"
        return AdapterResult(
            (
                RecordBusinessFact(
                    branch_id=source.branch_id,
                    subject_type="job",
                    subject_id=source.job_id,
                    category=EconomicCategory.REVENUE,
                    fact_key="invoice_revenue",
                    amount_minor=_minor_units(source.total_amount),
                    currency=source.currency,
                    confidence=Confidence(
                        MeasurementStatus.MEASURED,
                        100,
                        "Recorded from an authoritative issued invoice.",
                    ),
                    evidence=_evidence(
                        context=context,
                        source_system="acp_enterprise",
                        source_record_type="invoice",
                        reference_id=source.id,
                        source_version=version,
                        content=content,
                    ),
                    occurred_at=occurred_at,
                    period_start=occurred_at.date(),
                    period_end=occurred_at.date(),
                    measurement_method="issued_invoice_total",
                    accounting_basis="accrual",
                    effective_at=occurred_at,
                ),
            )
        )


class PaymentSourceAdapter:
    def adapt(self, source: PaymentSource, context: AdapterContext) -> AdapterResult:
        if source.status != "succeeded" or source.paid_at is None:
            return AdapterResult((), f"Payment {source.id} is not successful.")
        content: dict[str, object] = {
            "id": str(source.id),
            "company_id": str(source.company_id),
            "branch_id": str(source.branch_id),
            "invoice_id": str(source.invoice_id),
            "status": source.status,
            "currency": source.currency,
            "amount": str(source.amount),
            "paid_at": source.paid_at,
        }
        version = f"{source.status}:{source.paid_at.isoformat()}"
        return AdapterResult(
            (
                RecordBusinessFact(
                    branch_id=source.branch_id,
                    subject_type="invoice",
                    subject_id=source.invoice_id,
                    category=EconomicCategory.REVENUE,
                    fact_key="cash_collected",
                    amount_minor=_minor_units(source.amount),
                    currency=source.currency,
                    confidence=Confidence(
                        MeasurementStatus.MEASURED,
                        100,
                        "Recorded from an authoritative successful payment.",
                    ),
                    evidence=_evidence(
                        context=context,
                        source_system="acp_enterprise",
                        source_record_type="payment",
                        reference_id=source.id,
                        source_version=version,
                        content=content,
                    ),
                    occurred_at=source.paid_at,
                    period_start=source.paid_at.date(),
                    period_end=source.paid_at.date(),
                    measurement_method="successful_payment_amount",
                    accounting_basis="cash",
                    effective_at=source.paid_at,
                ),
            )
        )


class OperationalCostSourceAdapter:
    def __init__(self, category: EconomicCategory, record_type: str) -> None:
        self.category = category
        self.record_type = record_type

    def adapt(
        self, source: MeasuredOperationalCost, context: AdapterContext
    ) -> AdapterResult:
        if source.amount_minor < 0:
            raise EconomicsSourceAdapterError("measured source cost cannot be negative")
        content = asdict(source)
        return AdapterResult(
            (
                RecordBusinessFact(
                    branch_id=source.branch_id,
                    subject_type="job",
                    subject_id=source.job_id,
                    category=self.category,
                    fact_key=f"{self.record_type}_cost",
                    amount_minor=source.amount_minor,
                    currency=source.currency,
                    confidence=Confidence(
                        MeasurementStatus.MEASURED,
                        100,
                        f"Recorded from authoritative measured {self.record_type}.",
                    ),
                    evidence=_evidence(
                        context=context,
                        source_system="acp_enterprise",
                        source_record_type=self.record_type,
                        reference_id=source.id,
                        source_version=source.source_version,
                        content=content,
                    ),
                    occurred_at=source.occurred_at,
                    period_start=source.period_start,
                    period_end=source.period_end,
                    measurement_method=source.measurement_method,
                    accounting_basis="accrual",
                    effective_at=source.occurred_at,
                ),
            )
        )


labor_time_entry_adapter = OperationalCostSourceAdapter(
    EconomicCategory.LABOR, "labor_time_entry"
)
material_usage_adapter = OperationalCostSourceAdapter(
    EconomicCategory.MATERIALS, "material_usage"
)
equipment_utilization_adapter = OperationalCostSourceAdapter(
    EconomicCategory.EQUIPMENT, "equipment_utilization"
)
truck_activity_adapter = OperationalCostSourceAdapter(
    EconomicCategory.TRUCK, "truck_activity"
)


class BusinessEventSourceAdapter:
    def adapt(self, source: BusinessEvent, context: AdapterContext) -> AdapterResult:
        economics = source.payload.get("economics")
        if not isinstance(economics, dict):
            return AdapterResult(
                (), f"Business Event {source.id} has no economics fact."
            )
        required = {
            "category",
            "fact_key",
            "amount_minor",
            "currency",
            "period_start",
            "period_end",
        }
        if not required.issubset(economics):
            raise EconomicsSourceAdapterError(
                "Business Event economics payload is incomplete"
            )
        if economics.get("measurement_status") != "measured":
            return AdapterResult((), "Business Event economics value is not measured.")
        if (
            source.company_id is None
            or source.branch_id is None
            or source.entity_id is None
        ):
            raise EconomicsSourceAdapterError(
                "Business Event economics scope is incomplete"
            )
        try:
            category = EconomicCategory(str(economics["category"]))
            amount_minor = int(economics["amount_minor"])
            period_start = date.fromisoformat(str(economics["period_start"]))
            period_end = date.fromisoformat(str(economics["period_end"]))
        except (TypeError, ValueError) as error:
            raise EconomicsSourceAdapterError(
                "Business Event economics payload is invalid"
            ) from error
        content: dict[str, object] = {
            "id": str(source.id),
            "event_type": source.event_type,
            "entity_type": source.entity_type,
            "entity_id": str(source.entity_id),
            "payload": source.payload,
            "occurred_at": source.occurred_at,
        }
        evidence = EvidenceInput(
            kind=EvidenceKind.BUSINESS_EVENT,
            reference_id=str(source.id),
            source_system="acp_enterprise",
            source_record_type="business_event",
            source_version=context.business_event_version,
            content_digest=_digest(content),
            observed_at=context.observed_at,
            explanation="Authoritative measured economics Business Event.",
            business_event_id=source.id,
        )
        return AdapterResult(
            (
                RecordBusinessFact(
                    branch_id=source.branch_id,
                    subject_type=source.entity_type,
                    subject_id=source.entity_id,
                    category=category,
                    fact_key=str(economics["fact_key"]),
                    amount_minor=amount_minor,
                    currency=str(economics["currency"]),
                    confidence=Confidence(
                        MeasurementStatus.MEASURED,
                        100,
                        "Explicit measured value in authoritative Business Event.",
                    ),
                    evidence=(evidence,),
                    occurred_at=source.occurred_at,
                    period_start=period_start,
                    period_end=period_end,
                    measurement_method=str(
                        economics.get("measurement_method", "business_event_payload")
                    ),
                    accounting_basis=str(economics.get("accounting_basis", "accrual")),
                    effective_at=source.occurred_at,
                ),
            )
        )
