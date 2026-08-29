"""Source-faithful Financial supersession for line-item-empty HCP Invoices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from uuid import UUID, uuid5

from app.operational_migration.financial import (
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_hybrid_customer import canonical_sha256
from app.operational_migration.hcp_migration2b import PlanOutcomeCommand
from app.operational_migration.hcp_migration2i import ChildRepairPlan

FINANCIAL_SUPERSESSION_VERSION = "hcp-migration-2l-financial-supersession/v1"
INVOICE_EVIDENCE_REASON = "invoice_line_items_absent_source_evidence_only"
PAYMENT_EVIDENCE_REASON = "source_invoice_evidence_only"
FINANCIAL_SUPERSESSION_NAMESPACE = UUID("95a0ec46-64d7-54ad-9ce0-d7c4626ff4d8")


@dataclass(frozen=True)
class FinancialEvidenceDisposition:
    entity_kind: str
    source_identity_sha256: str
    parent_identity_sha256: str
    evidence_digest: str
    reason_code: str

    @property
    def disposition_digest(self) -> str:
        return canonical_sha256(
            {"contract": FINANCIAL_SUPERSESSION_VERSION, **asdict(self)}
        )

    def plan_outcome(self) -> PlanOutcomeCommand:
        command = PlanOutcomeCommand(
            entity_kind=self.entity_kind,
            native_identity_sha256=self.source_identity_sha256,
            outcome="EXPLICIT_EXCEPTION",
            reason_code=self.reason_code,
            evidence_digest=self.evidence_digest,
            transformation_version=FINANCIAL_SUPERSESSION_VERSION,
        )
        command.validate()
        return command


@dataclass(frozen=True)
class FinancialSupersedingPlan:
    id: UUID
    master_id: UUID
    original_repair_id: UUID
    nonconforming_child_id: UUID
    original_repair_plan_digest: str
    retained_invoice_identity_digests: tuple[str, ...]
    retained_payment_identity_digests: tuple[str, ...]
    invoice_evidence: tuple[FinancialEvidenceDisposition, ...]
    payment_evidence: tuple[FinancialEvidenceDisposition, ...]
    persisted_counts: dict[str, int]
    exception_counts: dict[str, int]
    digest: str

    @property
    def outcomes(self) -> tuple[PlanOutcomeCommand, ...]:
        return tuple(
            item.plan_outcome()
            for item in (*self.invoice_evidence, *self.payment_evidence)
        )


def _invoice_evidence(record: InvoiceMigrationRecord) -> FinancialEvidenceDisposition:
    if record.line_items:
        raise ValueError("native Invoice evidence unexpectedly contains line items")
    return FinancialEvidenceDisposition(
        entity_kind="invoice",
        source_identity_sha256=canonical_sha256(record.source_id),
        parent_identity_sha256=canonical_sha256(record.source_job_id),
        evidence_digest=canonical_sha256(
            {
                "source_identity": record.source_id,
                "job_identity": record.source_job_id,
                "status": record.status,
                "currency": record.currency,
                "subtotal": str(record.subtotal_amount),
                "tax": str(record.tax_amount),
                "total": str(record.total_amount),
                "issued_at": record.issued_at.isoformat() if record.issued_at else None,
                "due_on": record.due_on.isoformat() if record.due_on else None,
                "line_item_count": 0,
                "external_metadata": record.external_metadata or {},
            }
        ),
        reason_code=INVOICE_EVIDENCE_REASON,
    )


def _payment_evidence(record: PaymentMigrationRecord) -> FinancialEvidenceDisposition:
    return FinancialEvidenceDisposition(
        entity_kind="payment",
        source_identity_sha256=canonical_sha256(record.source_id),
        parent_identity_sha256=canonical_sha256(record.source_invoice_id),
        evidence_digest=canonical_sha256(
            {
                "source_identity": record.source_id,
                "invoice_identity": record.source_invoice_id,
                "status": record.status,
                "currency": record.currency,
                "amount": str(record.amount),
                "paid_at": record.paid_at.isoformat() if record.paid_at else None,
                "method": record.method,
                "reference": record.reference,
                "external_metadata": record.external_metadata or {},
            }
        ),
        reason_code=PAYMENT_EVIDENCE_REASON,
    )


def build_financial_superseding_plan(
    *,
    master_id: UUID,
    original_repair_id: UUID,
    nonconforming_child_id: UUID,
    repair: ChildRepairPlan,
) -> FinancialSupersedingPlan:
    """Reclassify non-native Invoice evidence without fabricating line items."""
    native_invoices = tuple(
        sorted(
            (item for item in repair.financial.invoices if item.line_items),
            key=lambda item: item.source_id,
        )
    )
    evidence_invoices = tuple(
        sorted(
            (item for item in repair.financial.invoices if not item.line_items),
            key=lambda item: item.source_id,
        )
    )
    evidence_invoice_ids = frozenset(item.source_id for item in evidence_invoices)
    native_payments = tuple(
        sorted(
            (
                item
                for item in repair.financial.payments
                if item.source_invoice_id not in evidence_invoice_ids
            ),
            key=lambda item: item.source_id,
        )
    )
    evidence_payments = tuple(
        sorted(
            (
                item
                for item in repair.financial.payments
                if item.source_invoice_id in evidence_invoice_ids
            ),
            key=lambda item: item.source_id,
        )
    )
    invoice_evidence = tuple(_invoice_evidence(item) for item in evidence_invoices)
    payment_evidence = tuple(_payment_evidence(item) for item in evidence_payments)
    persisted = dict(repair.persisted_counts)
    persisted["invoice"] = len(native_invoices)
    persisted["payment"] = len(native_payments)
    exceptions = dict(repair.exception_counts)
    exceptions["invoice"] = exceptions.get("invoice", 0) + len(invoice_evidence)
    exceptions["payment"] = exceptions.get("payment", 0) + len(payment_evidence)
    payload = {
        "version": FINANCIAL_SUPERSESSION_VERSION,
        "master_id": str(master_id),
        "original_repair_id": str(original_repair_id),
        "nonconforming_child_id": str(nonconforming_child_id),
        "original_repair_plan_digest": repair.repair_plan_digest,
        "retained_invoice_identity_digests": [
            canonical_sha256(item.source_id) for item in native_invoices
        ],
        "retained_payment_identity_digests": [
            canonical_sha256(item.source_id) for item in native_payments
        ],
        "invoice_evidence": [item.disposition_digest for item in invoice_evidence],
        "payment_evidence": [item.disposition_digest for item in payment_evidence],
        "persisted_counts": persisted,
        "exception_counts": exceptions,
        "financial_truth": False,
    }
    digest = canonical_sha256(payload)
    return FinancialSupersedingPlan(
        id=uuid5(FINANCIAL_SUPERSESSION_NAMESPACE, digest),
        master_id=master_id,
        original_repair_id=original_repair_id,
        nonconforming_child_id=nonconforming_child_id,
        original_repair_plan_digest=repair.repair_plan_digest,
        retained_invoice_identity_digests=tuple(
            payload["retained_invoice_identity_digests"]  # type: ignore[arg-type]
        ),
        retained_payment_identity_digests=tuple(
            payload["retained_payment_identity_digests"]  # type: ignore[arg-type]
        ),
        invoice_evidence=invoice_evidence,
        payment_evidence=payment_evidence,
        persisted_counts=dict(sorted(persisted.items())),
        exception_counts=dict(sorted(exceptions.items())),
        digest=digest,
    )


def superseding_completion_counts(
    repair: ChildRepairPlan, superseding: FinancialSupersedingPlan
) -> ChildRepairPlan:
    """Return completion accounting only; immutable repair commands stay unchanged."""
    return replace(
        repair,
        persisted_counts=superseding.persisted_counts,
        exception_counts=superseding.exception_counts,
        additional_plan_outcomes=(
            *repair.additional_plan_outcomes,
            *superseding.outcomes,
        ),
        repair_plan_digest=superseding.digest,
    )


def evidence_relationship_counts(
    *,
    invoices: Sequence[InvoiceMigrationRecord],
    payments: Sequence[PaymentMigrationRecord],
) -> tuple[int, int]:
    evidence_invoice_ids = frozenset(
        item.source_id for item in invoices if not item.line_items
    )
    related = tuple(
        item for item in payments if item.source_invoice_id in evidence_invoice_ids
    )
    return len({item.source_invoice_id for item in related}), len(related)
