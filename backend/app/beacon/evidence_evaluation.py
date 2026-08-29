"""Evidence-bound readiness and evaluator registry for operational signals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.beacon.catalog import (
    BEACON_SIGNAL_CATALOG,
    OPERATIONAL_SIGNAL_CATALOG,
    OperationalSignalCatalog,
    OperationalSignalFamily,
)
from app.beacon.contracts import BeaconSnapshot
from app.beacon.records import BeaconSignal

if TYPE_CHECKING:
    from app.beacon.evaluation import SignalEvaluationService


class EvaluationReadiness(StrEnum):
    EVALUABLE = "evaluable"
    PARTIALLY_EVALUABLE = "partially_evaluable"
    NOT_EVALUABLE = "not_evaluable"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class EvidenceEvaluationRegistration:
    definition_id: str
    family: OperationalSignalFamily
    readiness: EvaluationReadiness
    authoritative_source_contract: str
    required_fact_contract: tuple[str, ...]
    adapter_code: str | None
    evaluator_code: str | None
    blocker: str | None
    limitations: tuple[str, ...]

    @property
    def evaluator_implemented(self) -> bool:
        return self.adapter_code is not None and self.evaluator_code is not None


@dataclass(frozen=True)
class EvidenceEvaluationRegistry:
    registrations: tuple[EvidenceEvaluationRegistration, ...]
    catalog: OperationalSignalCatalog = OPERATIONAL_SIGNAL_CATALOG

    def __post_init__(self) -> None:
        catalog_ids = {
            definition.definition_id for definition in self.catalog.definitions
        }
        registration_ids = {
            registration.definition_id for registration in self.registrations
        }
        if registration_ids != catalog_ids:
            missing = sorted(catalog_ids - registration_ids)
            extra = sorted(registration_ids - catalog_ids)
            raise ValueError(
                f"Evaluation registry must cover the catalog; missing={missing}, extra={extra}."
            )
        if len(registration_ids) != len(self.registrations):
            raise ValueError("Evaluation registrations must be unique.")
        for registration in self.registrations:
            definition = self.catalog.definition(registration.definition_id)
            if registration.family is not definition.family:
                raise ValueError("Evaluation family must match the catalog definition.")
            if registration.readiness is EvaluationReadiness.EVALUABLE:
                if not registration.evaluator_implemented or registration.blocker:
                    raise ValueError(
                        "Evaluable definitions require an adapter/evaluator and no blocker."
                    )
            elif registration.evaluator_implemented or not registration.blocker:
                raise ValueError(
                    "Blocked definitions require an explicit blocker and no evaluator."
                )
            if not registration.required_fact_contract:
                raise ValueError("Every evaluation requires a named fact contract.")

    def registration(self, definition_id: str) -> EvidenceEvaluationRegistration:
        try:
            return next(
                item
                for item in self.registrations
                if item.definition_id == definition_id
            )
        except StopIteration as error:
            raise KeyError(definition_id) from error

    def evaluate_existing(
        self,
        snapshot: BeaconSnapshot,
        *,
        evaluator: SignalEvaluationService | None = None,
    ) -> tuple[BeaconSignal, ...]:
        """Run only accepted legacy evaluators and prove their catalog admission."""
        if evaluator is None:
            from app.beacon.evaluation import signal_evaluation_service

            evaluator = signal_evaluation_service
        signals = evaluator.evaluate_signals(snapshot)
        accepted_rule_codes = {
            registration.evaluator_code
            for registration in self.registrations
            if registration.readiness is EvaluationReadiness.EVALUABLE
        }
        for signal in signals:
            if signal.rule_code not in accepted_rule_codes:
                # The past-due invoice rule remains backward compatible but is outside
                # this operational catalog's admitted evaluation boundary.
                if signal.rule_code == "revenue.past_due_invoices":
                    continue
                raise ValueError(
                    f"Beacon evaluator {signal.rule_code} lacks catalog authority."
                )
        return signals


def _registration(
    definition_id: str,
    readiness: EvaluationReadiness,
    source_contract: str,
    required_facts: tuple[str, ...],
    blocker: str | None,
    *,
    adapter_code: str | None = None,
    evaluator_code: str | None = None,
    limitations: tuple[str, ...] = (),
) -> EvidenceEvaluationRegistration:
    definition = BEACON_SIGNAL_CATALOG.definition(definition_id)
    return EvidenceEvaluationRegistration(
        definition_id=definition_id,
        family=definition.family,
        readiness=readiness,
        authoritative_source_contract=source_contract,
        required_fact_contract=required_facts,
        adapter_code=adapter_code,
        evaluator_code=evaluator_code,
        blocker=blocker,
        limitations=limitations,
    )


PARTIAL = EvaluationReadiness.PARTIALLY_EVALUABLE
NONE = EvaluationReadiness.NOT_EVALUABLE

_ALL_REGISTRATIONS = (
    _registration(
        "operational.scheduling.appointment_unassigned",
        PARTIAL,
        "Scheduling Appointment plus DispatchAssignment",
        ("appointment_state", "assignment_state", "as_of_identity"),
        "No accepted as-of reconciliation contract defines when a committed appointment is unassigned.",
    ),
    _registration(
        "operational.scheduling.appointment_overdue",
        EvaluationReadiness.EVALUABLE,
        "SqlBeaconFactRepository.overdue_appointments",
        ("appointment_state", "arrival_window", "business_event"),
        None,
        adapter_code="beacon.sql_snapshot.overdue_appointments.v1",
        evaluator_code="scheduling.overdue_committed_appointments",
        limitations=("Company-wide aggregate; Branch evidence is not projected yet.",),
    ),
    _registration(
        "operational.scheduling.scheduled_start_missed",
        PARTIAL,
        "Scheduling Appointment and Dispatch arrival evidence",
        ("scheduled_start", "accepted_start_event", "tolerance_policy"),
        "Arrival windows exist, but no accepted scheduled-start tolerance and start-event contract exists.",
    ),
    _registration(
        "operational.scheduling.authoritative_conflict",
        PARTIAL,
        "Scheduling overlap query",
        ("conflict_record", "conflicting_fact_identities"),
        "Overlap detection exists, but no durable accepted scheduling-conflict evidence identity exists.",
    ),
    _registration(
        "operational.dispatch.job_awaiting_dispatch",
        PARTIAL,
        "Job, JobAppointmentLink, Appointment, and DispatchAssignment",
        (
            "dispatch_eligibility",
            "explicit_job_appointment_link",
            "assignment_state",
        ),
        "No accepted dispatch-eligibility fact contract defines when a linked Job must be dispatched.",
    ),
    _registration(
        "operational.dispatch.assigned_resource_unavailable",
        PARTIAL,
        "DispatchAssignment and WorkforceAvailability",
        (
            "assignment_state",
            "availability_evidence",
            "effective_time_reconciliation",
        ),
        "Assignment and availability exist, but their accepted effective-time reconciliation contract is absent.",
    ),
    _registration(
        "operational.dispatch.state_stalled",
        PARTIAL,
        "DispatchAssignment and DispatchAssignmentHistory",
        ("dispatch_state", "state_entered_at", "duration_policy"),
        "Dispatch history exists, but no accepted per-state stall duration policy exists.",
    ),
    _registration(
        "operational.dispatch.arrival_execution_mismatch",
        PARTIAL,
        "Dispatch arrival events and Job execution evidence",
        ("arrival_event", "execution_event", "accepted_reconciliation_identity"),
        "Both evidence families exist, but no accepted cross-domain mismatch contract resolves their identity and as-of scope.",
    ),
    _registration(
        "operational.job.intermediate_state_stalled",
        EvaluationReadiness.EVALUABLE,
        "SqlBeaconFactRepository.paused_jobs",
        ("job_state", "paused_at", "business_event"),
        None,
        adapter_code="beacon.sql_snapshot.paused_jobs.v1",
        evaluator_code="operations.paused_jobs",
        limitations=("Only the accepted paused state is evaluated.",),
    ),
    _registration(
        "operational.job.completion_evidence_inconsistent",
        PARTIAL,
        "Job completion guards and field completion evidence",
        ("completion_evidence", "conflicting_fact_identities"),
        "Completion evidence exists, but no accepted contradiction fact contract enumerates conflicting identities.",
    ),
    _registration(
        "operational.job.lifecycle_inconsistent",
        PARTIAL,
        "Job lifecycle state and transition history",
        ("job_state", "transition_evidence", "conflicting_fact_identities"),
        "Transitions are guarded, but no accepted historical inconsistency evidence contract exists.",
    ),
    _registration(
        "operational.job.follow_up_incomplete",
        NONE,
        "No authoritative required-follow-up domain contract",
        ("follow_up_requirement", "follow_up_state"),
        "ACP has no authoritative required operational follow-up record and lifecycle.",
    ),
    _registration(
        "operational.location.required_data_missing",
        PARTIAL,
        "Customer ServiceLocation records",
        ("requirement_identity", "field_presence_evidence"),
        "Service-location fields exist, but no accepted operational required-field policy identifies mandatory fields.",
    ),
    _registration(
        "operational.location.contact_condition_unresolved",
        NONE,
        "No authoritative operational contact-condition lifecycle",
        ("contact_condition", "condition_state"),
        "ACP has no authoritative unresolved operational contact/location condition record.",
    ),
    _registration(
        "operational.location.service_restriction_active",
        NONE,
        "No accepted Customer service-restriction policy record",
        ("service_policy_identity", "restriction_state"),
        "Workforce restrictions exist, but no authoritative Customer/service-location do-not-service policy exists.",
    ),
    _registration(
        "operational.estimate.approved_workflow_not_advanced",
        PARTIAL,
        "Estimate approval plus explicit EstimateConversionRecord",
        (
            "estimate_state",
            "explicit_workflow_link",
            "workflow_state",
            "duration_policy",
        ),
        "Explicit conversion identity exists, but no accepted not-advanced duration and target-state policy exists.",
    ),
    _registration(
        "operational.invoice.workflow_stalled",
        PARTIAL,
        "Invoice operational lifecycle",
        ("invoice_state", "state_entered_at", "duration_policy"),
        "Invoice states exist, but no accepted operational stall duration policy exists.",
        limitations=("Accounting and financial materiality are explicitly excluded.",),
    ),
    _registration(
        "operational.payment.evidence_inconsistent",
        PARTIAL,
        "Payment lifecycle and immutable evidence",
        ("payment_state", "conflicting_fact_identities"),
        "Payment evidence exists, but no accepted operational contradiction contract defines conflicting identities.",
        limitations=(
            "Settlement acceptance and Accounting source precedence are excluded.",
        ),
    ),
    _registration(
        "operational.workforce.assignment_ineligible",
        PARTIAL,
        "DispatchAssignment and workforce capability/availability facts",
        (
            "assignment_state",
            "eligibility_evidence",
            "effective_time_reconciliation",
        ),
        "Eligibility queries exist, but no immutable assignment-time eligibility evidence is accepted for replay.",
    ),
    _registration(
        "operational.workforce.capability_requirement_missing",
        PARTIAL,
        "Workforce capability profiles and dispatch requirements",
        (
            "capability_requirement",
            "qualification_evidence",
            "requirement_identity",
        ),
        "Capabilities exist, but Jobs do not own an accepted immutable capability-requirement identity.",
    ),
    _registration(
        "operational.workforce.staffing_availability_mismatch",
        PARTIAL,
        "DispatchAssignment and WorkforceAvailability",
        (
            "assignment_state",
            "availability_evidence",
            "effective_time_reconciliation",
        ),
        "Availability exists, but no accepted assignment-time reconciliation evidence is persisted for replay.",
    ),
    _registration(
        "financial.invoice.workflow_exception",
        EvaluationReadiness.EVALUABLE,
        "ACP Invoice/AR lifecycle and Accounting handoff",
        ("invoice_state", "accounting_status", "durable_handoff_evidence"),
        None,
        adapter_code="beacon.native_financial.invoice.v1",
        evaluator_code="financial.invoice.workflow_exception",
    ),
    _registration(
        "financial.receivable.strict_past_due",
        EvaluationReadiness.EVALUABLE,
        "ACP Invoice/AR open-item contract",
        ("invoice_state", "due_date", "open_amount", "as_of_identity"),
        None,
        adapter_code="beacon.native_financial.receivable.v1",
        evaluator_code="financial.receivable.strict_past_due",
        limitations=("No grace, collection urgency, or materiality semantics.",),
    ),
    _registration(
        "financial.payment.evidence_inconsistency",
        EvaluationReadiness.EVALUABLE,
        "ACP Payments reconciliation evidence",
        ("explicit_reconciliation_state", "durable_evidence_identity"),
        None,
        adapter_code="beacon.native_financial.payment_evidence.v1",
        evaluator_code="financial.payment.evidence_inconsistency",
    ),
    _registration(
        "financial.payment.application_mismatch",
        EvaluationReadiness.EVALUABLE,
        "ACP Payment receipt/application invariant",
        ("receipt_invariant", "application_identity", "reconciliation_identity"),
        None,
        adapter_code="beacon.native_financial.payment_application.v1",
        evaluator_code="financial.payment.application_mismatch",
    ),
    _registration(
        "financial.payment.unapplied",
        EvaluationReadiness.EVALUABLE,
        "ACP Payment receipt open-application state",
        ("receipt_identity", "available_amount", "application_state"),
        None,
        adapter_code="beacon.native_financial.unapplied_receipt.v1",
        evaluator_code="financial.payment.unapplied",
        limitations=("No age, urgency, abandonment, or materiality semantics.",),
    ),
    _registration(
        "financial.ap.bill_workflow_exception",
        EvaluationReadiness.EVALUABLE,
        "ACP Accounts Payable bill lifecycle and posting receipt",
        ("bill_state", "accounting_status", "durable_posting_evidence"),
        None,
        adapter_code="beacon.native_financial.ap_bill.v1",
        evaluator_code="financial.ap.bill_workflow_exception",
    ),
    _registration(
        "accounting.posting.failure",
        EvaluationReadiness.EVALUABLE,
        "ACP Accounting PostingFailure",
        ("posting_failure_identity", "correlation_identity", "source_digest"),
        None,
        adapter_code="beacon.accounting.posting_failure.v1",
        evaluator_code="accounting.posting.failure",
    ),
    _registration(
        "accounting.journal.rejected_or_integrity_failed",
        EvaluationReadiness.EVALUABLE,
        "ACP durable journal failure/audit evidence",
        ("journal_identity", "failure_state", "audit_identity"),
        None,
        adapter_code="beacon.accounting.journal_failure.v1",
        evaluator_code="accounting.journal.rejected_or_integrity_failed",
    ),
    _registration(
        "accounting.reconciliation.exception",
        EvaluationReadiness.EVALUABLE,
        "ACP native reconciliation and report quality contracts",
        ("reconciliation_state", "scope_identity", "cutoff_identity"),
        None,
        adapter_code="beacon.accounting.reconciliation.v1",
        evaluator_code="accounting.reconciliation.exception",
    ),
    _registration(
        "accounting.report.completeness_failure",
        EvaluationReadiness.EVALUABLE,
        "ACC.RPT.1 ReportQuality and ReportManifest",
        ("report_identity", "manifest_digest", "completeness_state"),
        None,
        adapter_code="beacon.accounting.report_completeness.v1",
        evaluator_code="accounting.report.completeness_failure",
    ),
    _registration(
        "accounting.report.integrity_failure",
        EvaluationReadiness.EVALUABLE,
        "ACC.RPT.1 integrity and provenance controls",
        ("report_or_failure_identity", "integrity_state", "provenance_digest"),
        None,
        adapter_code="beacon.accounting.report_integrity.v1",
        evaluator_code="accounting.report.integrity_failure",
    ),
    _registration(
        "accounting.period.control_violation",
        EvaluationReadiness.EVALUABLE,
        "ACP Accounting period and durable control rejection",
        ("period_identity", "effective_date", "control_rejection_identity"),
        None,
        adapter_code="beacon.accounting.period_control.v1",
        evaluator_code="accounting.period.control_violation",
    ),
)

EVIDENCE_EVALUATION_REGISTRY = EvidenceEvaluationRegistry(
    registrations=_ALL_REGISTRATIONS[:21],
)

BEACON_EVIDENCE_EVALUATION_REGISTRY = EvidenceEvaluationRegistry(
    registrations=_ALL_REGISTRATIONS,
    catalog=BEACON_SIGNAL_CATALOG,
)


__all__ = [
    "BEACON_EVIDENCE_EVALUATION_REGISTRY",
    "EVIDENCE_EVALUATION_REGISTRY",
    "EvaluationReadiness",
    "EvidenceEvaluationRegistration",
    "EvidenceEvaluationRegistry",
]
