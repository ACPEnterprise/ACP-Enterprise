"""Versioned product catalog for bounded operational Beacon exceptions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from app.beacon.contracts import (
    BeaconExpirationPolicy,
    BeaconPriorityBand,
    BeaconSeverity,
)


class OperationalSignalFamily(StrEnum):
    SCHEDULING = "scheduling"
    DISPATCH = "dispatch"
    JOB_LIFECYCLE = "job_lifecycle"
    CUSTOMER_LOCATION = "customer_service_location"
    ESTIMATE_WORKFLOW = "estimate_workflow"
    INVOICE_PAYMENT_WORKFLOW = "invoice_payment_workflow"
    WORKFORCE_TECHNICIAN = "workforce_technician"


class SignalClassification(StrEnum):
    OPERATIONAL = "operational"
    NATIVE_FINANCIAL_WORKFLOW = "native_financial_workflow"
    ACCOUNTING_CONTROL = "accounting_control"


class OperationalSignalAdmission(StrEnum):
    EVALUATED = "evaluated"
    REQUIRES_AUTHORITATIVE_ADAPTER = "requires_authoritative_adapter"


class OperationalConflictPolicy(StrEnum):
    FAIL_CLOSED = "fail_closed"
    SIGNAL_CONFLICT_EXISTENCE_ONLY = "signal_conflict_existence_only"


@dataclass(frozen=True)
class OperationalSignalDefinition:
    definition_id: str
    version: int
    family: OperationalSignalFamily
    subject_type: str
    source_authority: str
    condition: str
    explanation_safe_fields: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    base_severity: BeaconSeverity
    base_priority: BeaconPriorityBand
    expiration_policy: BeaconExpirationPolicy
    ttl_seconds: int
    conflict_policy: OperationalConflictPolicy
    admission: OperationalSignalAdmission
    evaluator_rule_code: str | None = None
    signal_classification: SignalClassification = SignalClassification.OPERATIONAL
    scope: Literal["company_and_optional_branch"] = "company_and_optional_branch"

    @property
    def definition_digest(self) -> str:
        return _digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "version": self.version,
            "family": self.family.value,
            "subject_type": self.subject_type,
            "source_authority": self.source_authority,
            "condition": self.condition,
            "explanation_safe_fields": self.explanation_safe_fields,
            "required_evidence_types": self.required_evidence_types,
            "base_severity": self.base_severity.value,
            "base_priority": self.base_priority.value,
            "expiration_policy": self.expiration_policy.value,
            "ttl_seconds": self.ttl_seconds,
            "conflict_policy": self.conflict_policy.value,
            "admission": self.admission.value,
            "evaluator_rule_code": self.evaluator_rule_code,
            "signal_classification": self.signal_classification.value,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class OperationalSignalIdentityInput:
    company_id: UUID
    branch_id: UUID | None
    subject_id: UUID
    evidence_digest: str
    source_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class OperationalSignalCatalog:
    catalog_id: str
    version: int
    definitions: tuple[OperationalSignalDefinition, ...]

    def __post_init__(self) -> None:
        identities = tuple(
            (definition.definition_id, definition.version)
            for definition in self.definitions
        )
        if len(identities) != len(set(identities)):
            raise ValueError(
                "Operational definition identity and version must be unique."
            )
        if len({item.definition_id for item in self.definitions}) != len(
            self.definitions
        ):
            raise ValueError("Only one active version is allowed per definition ID.")
        if any(item.version < 1 or item.ttl_seconds <= 0 for item in self.definitions):
            raise ValueError(
                "Operational definitions require positive versions and TTLs."
            )
        for item in self.definitions:
            if not item.required_evidence_types:
                raise ValueError("Operational definitions require explicit evidence.")
            if item.admission is OperationalSignalAdmission.EVALUATED:
                if item.evaluator_rule_code is None:
                    raise ValueError("Evaluated definitions require an evaluator rule.")
            elif item.evaluator_rule_code is not None:
                raise ValueError(
                    "Unadmitted definitions cannot name an evaluator rule."
                )

    @property
    def catalog_digest(self) -> str:
        return _digest(
            {
                "catalog_id": self.catalog_id,
                "version": self.version,
                "definitions": [item.payload() for item in self.definitions],
            }
        )

    def definition(self, definition_id: str) -> OperationalSignalDefinition:
        try:
            return next(
                item for item in self.definitions if item.definition_id == definition_id
            )
        except StopIteration as error:
            raise KeyError(definition_id) from error

    def signal_identity(
        self,
        definition_id: str,
        identity: OperationalSignalIdentityInput,
    ) -> UUID:
        definition = self.definition(definition_id)
        if len(identity.evidence_digest) != 64 or any(
            character not in "0123456789abcdef"
            for character in identity.evidence_digest
        ):
            raise ValueError("Signal identity requires a canonical evidence digest.")
        if not identity.source_evidence_ids or any(
            not value.strip() for value in identity.source_evidence_ids
        ):
            raise ValueError("Signal identity requires explicit source evidence IDs.")
        if len(identity.source_evidence_ids) != len(set(identity.source_evidence_ids)):
            raise ValueError("Source evidence identities must be unique.")
        payload = {
            "catalog_digest": self.catalog_digest,
            "definition_digest": definition.definition_digest,
            "company_id": str(identity.company_id),
            "branch_id": str(identity.branch_id)
            if identity.branch_id
            else "company-wide",
            "subject_type": definition.subject_type,
            "subject_id": str(identity.subject_id),
            "evidence_digest": identity.evidence_digest,
            "source_evidence_ids": sorted(identity.source_evidence_ids),
        }
        return uuid5(
            NAMESPACE_URL, json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )


def _digest(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _definition(
    definition_id: str,
    family: OperationalSignalFamily,
    subject_type: str,
    source_authority: str,
    condition: str,
    evidence: tuple[str, ...],
    *,
    severity: BeaconSeverity = BeaconSeverity.ATTENTION,
    priority: BeaconPriorityBand = BeaconPriorityBand.MONITOR,
    conflict: OperationalConflictPolicy = OperationalConflictPolicy.FAIL_CLOSED,
    evaluator_rule_code: str | None = None,
    classification: SignalClassification = SignalClassification.OPERATIONAL,
) -> OperationalSignalDefinition:
    return OperationalSignalDefinition(
        definition_id=definition_id,
        version=1,
        family=family,
        subject_type=subject_type,
        source_authority=source_authority,
        condition=condition,
        explanation_safe_fields=("subject_reference", "condition", "observed_at"),
        required_evidence_types=evidence,
        base_severity=severity,
        base_priority=priority,
        expiration_policy=BeaconExpirationPolicy.REPLACE_ON_NEXT_EVALUATION,
        ttl_seconds=900,
        conflict_policy=conflict,
        admission=(
            OperationalSignalAdmission.EVALUATED
            if evaluator_rule_code
            else OperationalSignalAdmission.REQUIRES_AUTHORITATIVE_ADAPTER
        ),
        evaluator_rule_code=evaluator_rule_code,
        signal_classification=classification,
    )


BANK_BEA_001_DEFINITIONS = (
    _definition(
        "operational.scheduling.appointment_unassigned",
        OperationalSignalFamily.SCHEDULING,
        "appointment",
        "Scheduling appointment and assignment records",
        "A committed appointment has no accepted active assignment.",
        ("appointment_state", "assignment_state"),
    ),
    _definition(
        "operational.scheduling.appointment_overdue",
        OperationalSignalFamily.SCHEDULING,
        "appointment",
        "Scheduling appointment records and accepted Business Events",
        "A committed appointment remains open after its arrival window.",
        ("appointment_state", "arrival_window", "business_event"),
        severity=BeaconSeverity.IMPORTANT,
        priority=BeaconPriorityBand.IMPORTANT,
        evaluator_rule_code="scheduling.overdue_committed_appointments",
    ),
    _definition(
        "operational.scheduling.scheduled_start_missed",
        OperationalSignalFamily.SCHEDULING,
        "appointment",
        "Scheduling appointment execution evidence",
        "No accepted start evidence exists after the scheduled start tolerance.",
        ("appointment_state", "scheduled_start", "execution_event"),
    ),
    _definition(
        "operational.scheduling.authoritative_conflict",
        OperationalSignalFamily.SCHEDULING,
        "appointment",
        "Scheduling conflict evidence contract",
        "Accepted scheduling facts explicitly report a conflict.",
        ("conflict_record", "conflicting_fact_identities"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
    _definition(
        "operational.dispatch.job_awaiting_dispatch",
        OperationalSignalFamily.DISPATCH,
        "job",
        "Dispatch job queue",
        "A dispatch-eligible job has no accepted dispatch outcome.",
        ("job_state", "dispatch_state"),
    ),
    _definition(
        "operational.dispatch.assigned_resource_unavailable",
        OperationalSignalFamily.DISPATCH,
        "dispatch_assignment",
        "Dispatch assignment and accepted availability evidence",
        "An active assignment references a resource explicitly reported unavailable.",
        ("assignment_state", "availability_evidence"),
    ),
    _definition(
        "operational.dispatch.state_stalled",
        OperationalSignalFamily.DISPATCH,
        "dispatch_assignment",
        "Dispatch lifecycle records",
        "A dispatch assignment exceeds its definition-owned state duration.",
        ("dispatch_state", "state_entered_at"),
    ),
    _definition(
        "operational.dispatch.arrival_execution_mismatch",
        OperationalSignalFamily.DISPATCH,
        "dispatch_assignment",
        "Accepted dispatch and job execution events",
        "Accepted arrival and execution states are explicitly inconsistent.",
        ("arrival_event", "execution_event"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
    _definition(
        "operational.job.intermediate_state_stalled",
        OperationalSignalFamily.JOB_LIFECYCLE,
        "job",
        "Job lifecycle records and Business Events",
        "A job remains in a bounded intermediate state past its rule duration.",
        ("job_state", "state_entered_at", "business_event"),
        evaluator_rule_code="operations.paused_jobs",
    ),
    _definition(
        "operational.job.completion_evidence_inconsistent",
        OperationalSignalFamily.JOB_LIFECYCLE,
        "job",
        "Job completion evidence contract",
        "Accepted completion evidence contains an explicit unresolved conflict.",
        ("completion_evidence", "conflicting_fact_identities"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
    _definition(
        "operational.job.lifecycle_inconsistent",
        OperationalSignalFamily.JOB_LIFECYCLE,
        "job",
        "Job lifecycle transition history",
        "Accepted lifecycle evidence contains an explicit transition conflict.",
        ("job_state", "transition_evidence", "conflicting_fact_identities"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
    _definition(
        "operational.job.follow_up_incomplete",
        OperationalSignalFamily.JOB_LIFECYCLE,
        "job",
        "Job-required operational follow-up records",
        "An explicitly required operational follow-up remains incomplete.",
        ("follow_up_requirement", "follow_up_state"),
    ),
    _definition(
        "operational.location.required_data_missing",
        OperationalSignalFamily.CUSTOMER_LOCATION,
        "service_location",
        "Service-location operational requirements",
        "A required operational location field is explicitly absent.",
        ("requirement_identity", "field_presence_evidence"),
    ),
    _definition(
        "operational.location.contact_condition_unresolved",
        OperationalSignalFamily.CUSTOMER_LOCATION,
        "service_location",
        "Customer and service-location operational contact conditions",
        "An accepted operational contact condition remains unresolved.",
        ("contact_condition", "condition_state"),
    ),
    _definition(
        "operational.location.service_restriction_active",
        OperationalSignalFamily.CUSTOMER_LOCATION,
        "service_location",
        "Accepted Customer service policy",
        "An explicit do-not-service or restricted-service condition is active.",
        ("service_policy_identity", "restriction_state"),
        severity=BeaconSeverity.IMPORTANT,
    ),
    _definition(
        "operational.estimate.approved_workflow_not_advanced",
        OperationalSignalFamily.ESTIMATE_WORKFLOW,
        "estimate",
        "Explicit accepted Estimate-to-workflow relationship",
        "An approved estimate with an explicit workflow link has not advanced.",
        ("estimate_state", "explicit_workflow_link", "workflow_state"),
    ),
    _definition(
        "operational.invoice.workflow_stalled",
        OperationalSignalFamily.INVOICE_PAYMENT_WORKFLOW,
        "invoice",
        "Invoice operational lifecycle contract",
        "An invoice remains in an explicit operational workflow state past its rule duration.",
        ("invoice_state", "state_entered_at"),
    ),
    _definition(
        "operational.payment.evidence_inconsistent",
        OperationalSignalFamily.INVOICE_PAYMENT_WORKFLOW,
        "payment",
        "Accepted payment operational evidence contract",
        "Accepted payment workflow evidence contains an explicit unresolved conflict.",
        ("payment_state", "conflicting_fact_identities"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
    _definition(
        "operational.workforce.assignment_ineligible",
        OperationalSignalFamily.WORKFORCE_TECHNICIAN,
        "dispatch_assignment",
        "Accepted assignment eligibility evidence",
        "An active assignment explicitly lacks an eligible technician.",
        ("assignment_state", "eligibility_evidence"),
    ),
    _definition(
        "operational.workforce.capability_requirement_missing",
        OperationalSignalFamily.WORKFORCE_TECHNICIAN,
        "job",
        "Job capability requirements and technician qualifications",
        "An explicit job capability requirement has no accepted qualified assignment.",
        ("capability_requirement", "qualification_evidence"),
    ),
    _definition(
        "operational.workforce.staffing_availability_mismatch",
        OperationalSignalFamily.WORKFORCE_TECHNICIAN,
        "dispatch_assignment",
        "Accepted staffing and availability evidence",
        "An assignment explicitly conflicts with accepted technician availability.",
        ("assignment_state", "availability_evidence"),
        conflict=OperationalConflictPolicy.SIGNAL_CONFLICT_EXISTENCE_ONLY,
    ),
)


def _financial_definition(
    definition_id: str,
    classification: SignalClassification,
    subject_type: str,
    source_authority: str,
    condition: str,
    evidence: tuple[str, ...],
    *,
    severity: BeaconSeverity = BeaconSeverity.ATTENTION,
) -> OperationalSignalDefinition:
    family = OperationalSignalFamily.INVOICE_PAYMENT_WORKFLOW
    return _definition(
        definition_id,
        family,
        subject_type,
        source_authority,
        condition,
        evidence,
        severity=severity,
        priority=BeaconPriorityBand.IMPORTANT,
        evaluator_rule_code=definition_id,
        classification=classification,
    )


BANK_BEA_007A_DEFINITIONS = (
    _financial_definition(
        "financial.invoice.workflow_exception",
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        "invoice",
        "ACP Invoice/AR lifecycle and Accounting handoff",
        "An authoritative invoice explicitly requires reconciliation or reports a failed handoff/lifecycle.",
        ("invoice_state", "accounting_status", "handoff_evidence"),
    ),
    _financial_definition(
        "financial.receivable.strict_past_due",
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        "invoice",
        "ACP Invoice/AR open-item contract",
        "An open native receivable has a contractual due date before the deterministic as-of date.",
        ("invoice_state", "due_date", "open_amount", "as_of_identity"),
    ),
    _financial_definition(
        "financial.payment.evidence_inconsistency",
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        "payment",
        "ACP Payments reconciliation evidence",
        "Native payment evidence explicitly records an unresolved inconsistency.",
        ("payment_state", "reconciliation_exception", "evidence_digest"),
    ),
    _financial_definition(
        "financial.payment.application_mismatch",
        SignalClassification.ACCOUNTING_CONTROL,
        "payment_receipt",
        "ACP Payment receipt/application invariant",
        "Accepted native payment/application evidence explicitly fails its amount or identity invariant.",
        ("receipt_amounts", "application_identities", "reconciliation_identity"),
    ),
    _financial_definition(
        "financial.payment.unapplied",
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        "payment_receipt",
        "ACP Payment receipt open-application state",
        "A native receipt has a positive amount remaining unapplied.",
        ("receipt_state", "available_amount", "application_state"),
    ),
    _financial_definition(
        "financial.ap.bill_workflow_exception",
        SignalClassification.NATIVE_FINANCIAL_WORKFLOW,
        "vendor_bill",
        "ACP Accounts Payable bill lifecycle and posting receipt",
        "A native vendor bill explicitly reports rejection, reconciliation-required, or failed posting workflow.",
        ("bill_state", "accounting_status", "posting_receipt"),
    ),
    _financial_definition(
        "accounting.posting.failure",
        SignalClassification.ACCOUNTING_CONTROL,
        "accounting_posting_failure",
        "ACP Accounting PostingFailure and Business Event",
        "A durable native Accounting posting failure exists.",
        ("posting_failure", "correlation_identity", "source_digest"),
        severity=BeaconSeverity.IMPORTANT,
    ),
    _financial_definition(
        "accounting.journal.rejected_or_integrity_failed",
        SignalClassification.ACCOUNTING_CONTROL,
        "accounting_journal",
        "ACP Accounting journal failure/audit evidence",
        "A durable rejected journal or journal-integrity failure exists.",
        ("journal_state", "durable_failure_evidence", "audit_identity"),
        severity=BeaconSeverity.IMPORTANT,
    ),
    _financial_definition(
        "accounting.reconciliation.exception",
        SignalClassification.ACCOUNTING_CONTROL,
        "accounting_reconciliation",
        "ACP native reconciliation and report quality contracts",
        "Compatible native scope and cutoff evidence explicitly reports reconciliation required or unreconciled.",
        ("reconciliation_state", "scope_identity", "cutoff_identity"),
        severity=BeaconSeverity.IMPORTANT,
    ),
    _financial_definition(
        "accounting.report.completeness_failure",
        SignalClassification.ACCOUNTING_CONTROL,
        "financial_report",
        "ACC.RPT.1 ReportQuality and ReportManifest",
        "An explicitly produced native report has incomplete quality state.",
        ("report_manifest", "report_quality", "missing_control_identities"),
        severity=BeaconSeverity.IMPORTANT,
    ),
    _financial_definition(
        "accounting.report.integrity_failure",
        SignalClassification.ACCOUNTING_CONTROL,
        "financial_report",
        "ACC.RPT.1 integrity and provenance controls",
        "An explicitly produced report or durable reporting failure has failed integrity.",
        ("report_manifest_or_failure", "integrity_state", "provenance_digest"),
        severity=BeaconSeverity.CRITICAL,
    ),
    _financial_definition(
        "accounting.period.control_violation",
        SignalClassification.ACCOUNTING_CONTROL,
        "accounting_period",
        "ACP Accounting period and durable control rejection",
        "A durable native posting/cutoff rejection proves a closed-period or period-bound violation.",
        ("period_identity", "effective_date", "durable_control_rejection"),
        severity=BeaconSeverity.IMPORTANT,
    ),
)


OPERATIONAL_SIGNAL_CATALOG = OperationalSignalCatalog(
    catalog_id="BANK.BEA.001",
    version=1,
    definitions=BANK_BEA_001_DEFINITIONS,
)

NATIVE_FINANCIAL_SIGNAL_CATALOG = OperationalSignalCatalog(
    catalog_id="BANK.BEA.007A",
    version=1,
    definitions=BANK_BEA_007A_DEFINITIONS,
)

BEACON_SIGNAL_CATALOG = OperationalSignalCatalog(
    catalog_id="BANK.BEA",
    version=7,
    definitions=BANK_BEA_001_DEFINITIONS + BANK_BEA_007A_DEFINITIONS,
)


__all__ = [
    "BANK_BEA_001_DEFINITIONS",
    "BANK_BEA_007A_DEFINITIONS",
    "BEACON_SIGNAL_CATALOG",
    "NATIVE_FINANCIAL_SIGNAL_CATALOG",
    "OPERATIONAL_SIGNAL_CATALOG",
    "OperationalConflictPolicy",
    "OperationalSignalAdmission",
    "OperationalSignalCatalog",
    "OperationalSignalDefinition",
    "OperationalSignalFamily",
    "OperationalSignalIdentityInput",
    "SignalClassification",
]
