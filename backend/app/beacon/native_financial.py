"""Evidence-bound native financial workflow and Accounting control signals.

This module consumes only explicit accepted ACP facts.  It does not query source
domains, infer cross-source identity, apply Finance policy, or mutate anything.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from uuid import NAMESPACE_URL, UUID, uuid5

from app.beacon.catalog import NATIVE_FINANCIAL_SIGNAL_CATALOG, SignalClassification
from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidence,
    BeaconConfidenceLevel,
    BeaconExpirationPolicy,
    BeaconLifecycleStatus,
    BeaconSignalSource,
)
from app.beacon.quality import (
    BEACON_EVIDENCE_QUALITY_SERVICE,
    EvidenceCompletenessState,
    EvidenceQualityInput,
    EvidenceReconciliationState,
    EvidenceTemporalBasis,
)
from app.beacon.records import (
    BeaconLifecycleProjection,
    BeaconPriority,
    BeaconSignal,
    BeaconSupportingFact,
)


class NativeFinancialSource(StrEnum):
    INVOICE_AR = "invoice_ar"
    PAYMENTS = "payments"
    ACCOUNTS_PAYABLE = "accounts_payable"
    ACCOUNTING_CORE = "accounting_core"
    ACCOUNTING_POSTING = "accounting_posting"
    FINANCIAL_REPORTING = "financial_reporting"


class NativeFinancialEvidenceConflict(ValueError):
    """Accepted evidence conflicts and cannot be admitted."""


NativeFactValue = str | int | bool


@dataclass(frozen=True)
class NativeFinancialFact:
    definition_id: str
    company_id: UUID
    branch_id: UUID | None
    subject_id: UUID
    source: NativeFinancialSource
    source_aggregate_id: UUID
    evidence_identities: tuple[str, ...]
    evidence_digest: str
    observed_at: datetime
    as_of: datetime
    attributes: Mapping[str, NativeFactValue]
    reconciliation_identity: str | None = None
    cutoff_identity: str | None = None
    conflict_identities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True)
class NativeFinancialEvaluation:
    signal: BeaconSignal | None
    definition_id: str
    classification: SignalClassification
    condition_met: bool
    resolution_source: str


_SOURCE_BY_DEFINITION = {
    "financial.invoice.workflow_exception": NativeFinancialSource.INVOICE_AR,
    "financial.receivable.strict_past_due": NativeFinancialSource.INVOICE_AR,
    "financial.payment.evidence_inconsistency": NativeFinancialSource.PAYMENTS,
    "financial.payment.application_mismatch": NativeFinancialSource.PAYMENTS,
    "financial.payment.unapplied": NativeFinancialSource.PAYMENTS,
    "financial.ap.bill_workflow_exception": NativeFinancialSource.ACCOUNTS_PAYABLE,
    "accounting.posting.failure": NativeFinancialSource.ACCOUNTING_POSTING,
    "accounting.journal.rejected_or_integrity_failed": NativeFinancialSource.ACCOUNTING_CORE,
    "accounting.reconciliation.exception": NativeFinancialSource.ACCOUNTING_CORE,
    "accounting.report.completeness_failure": NativeFinancialSource.FINANCIAL_REPORTING,
    "accounting.report.integrity_failure": NativeFinancialSource.FINANCIAL_REPORTING,
    "accounting.period.control_violation": NativeFinancialSource.ACCOUNTING_CORE,
}

_OPEN_INVOICE_STATES = {"issued", "partially_paid", "adjusted"}
_INVOICE_EXCEPTION_STATES = {"invalid_lifecycle", "handoff_failed"}
_AP_EXCEPTION_STATES = {"rejected", "workflow_failed"}
_RECONCILIATION_STATES = {"reconciliation_required", "unreconciled"}


class NativeFinancialSignalEvaluator:
    """Definition-bound, replayable evaluation of accepted native facts."""

    def evaluate(self, fact: NativeFinancialFact) -> NativeFinancialEvaluation:
        definition = NATIVE_FINANCIAL_SIGNAL_CATALOG.definition(fact.definition_id)
        if definition.signal_classification is SignalClassification.OPERATIONAL:
            raise ValueError(
                "Native financial evaluator cannot consume operational definitions."
            )
        expected_source = _SOURCE_BY_DEFINITION.get(fact.definition_id)
        if expected_source is None or fact.source is not expected_source:
            raise ValueError(
                "Definition source does not match its accepted ACP authority."
            )
        self._validate_evidence(fact)
        if fact.conflict_identities:
            raise NativeFinancialEvidenceConflict(
                "Conflicting accepted evidence has no approved precedence."
            )
        condition, safe_facts, resolution = self._condition(fact)
        if not condition:
            return NativeFinancialEvaluation(
                signal=None,
                definition_id=fact.definition_id,
                classification=definition.signal_classification,
                condition_met=False,
                resolution_source=resolution,
            )
        temporal_basis = (
            EvidenceTemporalBasis.DETERMINISTIC_AS_OF
            if fact.definition_id
            in {
                "financial.receivable.strict_past_due",
                "financial.payment.unapplied",
                "financial.invoice.workflow_exception",
                "financial.ap.bill_workflow_exception",
            }
            else EvidenceTemporalBasis.DURABLE_EVENT
        )
        quality = BEACON_EVIDENCE_QUALITY_SERVICE.evaluate(
            EvidenceQualityInput(
                definition_id=fact.definition_id,
                source_authority=definition.source_authority,
                evidence_identities=fact.evidence_identities,
                effective_at=fact.observed_at,
                observed_as_of=fact.as_of,
                evaluated_at=fact.as_of,
                completeness=EvidenceCompletenessState.COMPLETE,
                reconciliation=EvidenceReconciliationState.RECONCILED,
                limitations=(
                    "Native ACP fact only; no Finance, external-source, or Economics interpretation.",
                ),
                evidence_digest=fact.evidence_digest,
                temporal_basis=temporal_basis,
            )
        )
        if not quality.conclusion_admissible:
            raise ValueError("Native financial evidence did not pass Beacon admission.")
        signal_id = NATIVE_FINANCIAL_SIGNAL_CATALOG.signal_identity(
            fact.definition_id,
            self._identity_input(fact),
        )
        condition_key = uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    "beacon-native-financial-condition-v1",
                    str(fact.company_id),
                    str(fact.branch_id) if fact.branch_id else "company-wide",
                    fact.definition_id,
                    str(fact.subject_id),
                )
            ),
        )
        supporting = tuple(
            BeaconSupportingFact(
                name=name,
                value=value,
                source=fact.source.value,
                measured_at=fact.as_of,
            )
            for name, value in sorted(safe_facts.items())
        )
        priority = BeaconPriority(
            band=definition.base_priority,
            score=0,
            rank=0,
            ranking_factors=(),
            explanation="Definition-driven operational attention; no amount contributes.",
            evaluated_at=fact.as_of,
            tie_break_semantics="Severity, definition priority band, then stable signal identity.",
        )
        signal = BeaconSignal(
            id=signal_id,
            condition_key=condition_key,
            evidence_digest=fact.evidence_digest,
            definition_id=definition.definition_id,
            definition_version=definition.version,
            rule_code=definition.evaluator_rule_code or definition.definition_id,
            source=self._legacy_source(fact.source),
            title=definition.condition,
            category=BeaconCategory.REVENUE,
            severity=definition.base_severity,
            priority=priority,
            lifecycle=BeaconLifecycleProjection(
                status=BeaconLifecycleStatus.ACTIVE,
                latest_event=None,
                temporarily_suppressed=False,
            ),
            confidence=BeaconConfidence(
                level=BeaconConfidenceLevel.HIGH,
                basis="Explicit accepted native ACP evidence passed deterministic admission.",
            ),
            evidence_quality=quality,
            supporting_facts=supporting,
            recommended_action="Review the authoritative source condition; Beacon cannot alter it.",
            created_at=fact.as_of,
            expires_at=fact.as_of + timedelta(seconds=definition.ttl_seconds),
            expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
        )
        return NativeFinancialEvaluation(
            signal=signal,
            definition_id=fact.definition_id,
            classification=definition.signal_classification,
            condition_met=True,
            resolution_source=resolution,
        )

    @staticmethod
    def _identity_input(fact: NativeFinancialFact):
        from app.beacon.catalog import OperationalSignalIdentityInput

        return OperationalSignalIdentityInput(
            company_id=fact.company_id,
            branch_id=fact.branch_id,
            subject_id=fact.subject_id,
            evidence_digest=fact.evidence_digest,
            source_evidence_ids=fact.evidence_identities,
        )

    @staticmethod
    def _legacy_source(source: NativeFinancialSource) -> BeaconSignalSource:
        if source is NativeFinancialSource.INVOICE_AR:
            return BeaconSignalSource.INVOICES
        if source is NativeFinancialSource.PAYMENTS:
            return BeaconSignalSource.PAYMENTS
        if source is NativeFinancialSource.ACCOUNTS_PAYABLE:
            return BeaconSignalSource.ACCOUNTS_PAYABLE
        if source is NativeFinancialSource.FINANCIAL_REPORTING:
            return BeaconSignalSource.FINANCIAL_REPORTING
        return BeaconSignalSource.ACCOUNTING

    @staticmethod
    def _validate_evidence(fact: NativeFinancialFact) -> None:
        if len(fact.evidence_digest) != 64 or any(
            item not in "0123456789abcdef" for item in fact.evidence_digest
        ):
            raise ValueError("A canonical SHA-256 evidence digest is required.")
        if not fact.evidence_identities or any(
            not item.strip() for item in fact.evidence_identities
        ):
            raise ValueError("Explicit authoritative evidence identities are required.")
        if len(set(fact.evidence_identities)) != len(fact.evidence_identities):
            raise ValueError("Evidence identities must be unique.")
        forbidden = {"qbo", "quickbooks", "hcp", "migration", "economics", "eco"}
        if any(token in fact.source.value for token in forbidden):
            raise ValueError("External, Migration, and Economics evidence is excluded.")
        if fact.as_of.tzinfo is None or fact.observed_at.tzinfo is None:
            raise ValueError(
                "Evidence and evaluation timestamps must be timezone-aware."
            )

    def _condition(
        self, fact: NativeFinancialFact
    ) -> tuple[bool, dict[str, NativeFactValue], str]:
        attrs = fact.attributes
        definition_id = fact.definition_id
        if definition_id == "financial.invoice.workflow_exception":
            condition = (
                self._text(attrs, "accounting_status") == "reconciliation_required"
                or self._text(attrs, "invoice_state") in _INVOICE_EXCEPTION_STATES
                or self._bool(attrs, "durable_handoff_failure")
            )
            return (
                condition,
                {"explicit_native_exception": condition},
                "Invoice/AR lifecycle or accepted handoff evidence",
            )
        if definition_id == "financial.receivable.strict_past_due":
            due_date = self._date(attrs, "due_date")
            open_amount = self._decimal(attrs, "open_amount")
            condition = (
                due_date is not None
                and open_amount is not None
                and due_date < fact.as_of.date()
                and open_amount > 0
                and self._text(attrs, "invoice_state") in _OPEN_INVOICE_STATES
            )
            return (
                condition,
                {
                    "contractual_due_date_passed": condition,
                    "has_open_balance": bool(open_amount and open_amount > 0),
                },
                "Invoice due date, open amount, and lifecycle",
            )
        if definition_id == "financial.payment.evidence_inconsistency":
            condition = (
                self._text(attrs, "payment_state") == "reconciliation_required"
                or self._bool(attrs, "durable_reconciliation_exception")
                or self._bool(attrs, "durable_provider_evidence_conflict")
            )
            return (
                condition,
                {"explicit_native_inconsistency": condition},
                "Payments reconciliation evidence",
            )
        if definition_id == "financial.payment.application_mismatch":
            condition = self._bool(attrs, "invariant_failed") and bool(
                fact.reconciliation_identity
            )
            return (
                condition,
                {"native_application_invariant_failed": condition},
                "Payment application/reversal reconciliation",
            )
        if definition_id == "financial.payment.unapplied":
            amount = self._decimal(attrs, "available_amount")
            condition = (
                amount is not None
                and amount > 0
                and self._text(attrs, "receipt_state") == "unapplied"
            )
            return (
                condition,
                {"has_unapplied_value": condition},
                "Native Payment receipt/application state",
            )
        if definition_id == "financial.ap.bill_workflow_exception":
            condition = (
                self._text(attrs, "accounting_status") == "reconciliation_required"
                or self._text(attrs, "bill_state") in _AP_EXCEPTION_STATES
                or self._bool(attrs, "durable_posting_failure")
            )
            return (
                condition,
                {"explicit_native_exception": condition},
                "AP bill lifecycle or posting receipt",
            )
        if definition_id == "accounting.posting.failure":
            condition = self._bool(attrs, "durable_failure") and bool(
                fact.reconciliation_identity
            )
            return (
                condition,
                {"durable_posting_failure": condition},
                "Accounting PostingFailure/reconciliation receipt",
            )
        if definition_id == "accounting.journal.rejected_or_integrity_failed":
            condition = self._bool(attrs, "durable_failure") and self._text(
                attrs, "journal_state"
            ) in {"rejected", "integrity_failed"}
            return (
                condition,
                {"durable_journal_failure": condition},
                "Accounting journal/audit evidence",
            )
        if definition_id == "accounting.reconciliation.exception":
            condition = (
                self._text(attrs, "reconciliation_state") in _RECONCILIATION_STATES
                and bool(fact.reconciliation_identity)
                and bool(fact.cutoff_identity)
            )
            return (
                condition,
                {"explicit_unreconciled_state": condition},
                "Accepted reconciliation with matching scope and cutoff",
            )
        if definition_id == "accounting.report.completeness_failure":
            condition = (
                self._bool(attrs, "report_produced")
                and self._text(attrs, "completeness") == "incomplete"
                and bool(fact.cutoff_identity)
            )
            return (
                condition,
                {"explicit_incomplete_report": condition},
                "ACC.RPT.1 report quality",
            )
        if definition_id == "accounting.report.integrity_failure":
            condition = (
                self._bool(attrs, "durable_failure")
                and self._text(attrs, "integrity") == "failed"
            )
            return (
                condition,
                {"explicit_report_integrity_failure": condition},
                "ACC.RPT.1 integrity/provenance evidence",
            )
        if definition_id == "accounting.period.control_violation":
            condition = self._bool(attrs, "durable_rejection") and self._text(
                attrs, "violation_code"
            ) in {
                "closed_period",
                "effective_date_outside_period",
                "cutoff_control_rejected",
            }
            return (
                condition,
                {"explicit_period_control_violation": condition},
                "Accounting period/control rejection",
            )
        raise KeyError(definition_id)

    @staticmethod
    def _text(values: Mapping[str, NativeFactValue], key: str) -> str | None:
        value = values.get(key)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _bool(values: Mapping[str, NativeFactValue], key: str) -> bool:
        return values.get(key) is True

    @staticmethod
    def _decimal(values: Mapping[str, NativeFactValue], key: str) -> Decimal | None:
        value = values.get(key)
        if isinstance(value, bool) or value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None

    @staticmethod
    def _date(values: Mapping[str, NativeFactValue], key: str) -> date | None:
        value = values.get(key)
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


def canonical_native_fact_digest(fact: NativeFinancialFact) -> str:
    """Digest a sanitized adapter envelope for deterministic replay tests."""
    payload = {
        "definition_id": fact.definition_id,
        "company_id": str(fact.company_id),
        "branch_id": str(fact.branch_id) if fact.branch_id else None,
        "subject_id": str(fact.subject_id),
        "source": fact.source.value,
        "source_aggregate_id": str(fact.source_aggregate_id),
        "evidence_identities": sorted(fact.evidence_identities),
        "evidence_digest": fact.evidence_digest,
        "observed_at": fact.observed_at.isoformat(),
        "as_of": fact.as_of.isoformat(),
        "attributes": dict(sorted(fact.attributes.items())),
        "reconciliation_identity": fact.reconciliation_identity,
        "cutoff_identity": fact.cutoff_identity,
        "conflict_identities": sorted(fact.conflict_identities),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


native_financial_signal_evaluator = NativeFinancialSignalEvaluator()


__all__ = [
    "NativeFinancialEvaluation",
    "NativeFinancialEvidenceConflict",
    "NativeFinancialFact",
    "NativeFinancialSignalEvaluator",
    "NativeFinancialSource",
    "canonical_native_fact_digest",
    "native_financial_signal_evaluator",
]
