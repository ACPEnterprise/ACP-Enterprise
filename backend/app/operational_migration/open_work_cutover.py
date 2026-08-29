"""HCP.OPEN-WORK.1 deterministic August 21 cutover selection contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

OPEN_WORK_CONTRACT_VERSION = "hcp-open-work-cutover/2026-08-21/v1"
OPEN_WORK_NAMESPACE = UUID("e52d4ec8-8211-565c-9426-658f6edb242e")
TARGET_OPERATIONAL_FREEZE_DATE = date(2026, 8, 20)
OPERATIONAL_TIMEZONE = ZoneInfo("America/New_York")
DAY_ONE_INCLUDED_ENTITIES = (
    "customer",
    "contact",
    "service_location",
    "employee",
    "job",
    "appointment",
    "estimate",
    "note",
    "attachment",
    "invoice",
    "payment",
)
HISTORICAL_EXCLUSIONS_REMAIN = ("estimate", "note", "attachment")


class WorkDisposition(StrEnum):
    COMPLETE_IN_HCP = "complete_in_hcp"
    MIGRATE_TO_ENTERPRISE = "migrate_to_enterprise"
    EXPLICITLY_HELD = "explicitly_held"


class SelectionOutcome(StrEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"
    REJECTED = "rejected"
    OWNER_DISPOSITION_REQUIRED = "owner_disposition_required"


class NoteReason(StrEnum):
    ACTIVE_OPEN_WORK = "active_open_work"
    SAFETY = "safety"
    PROPERTY_ACCESS = "property_access"
    WARRANTY = "warranty"
    CUSTOMER_COMMITMENT = "customer_commitment"


class ArtifactReason(StrEnum):
    PERFORM_OPEN_WORK = "perform_open_work"
    PROVE_OPEN_WORK = "prove_open_work"


@dataclass(frozen=True)
class SourceEvidence:
    provider: str
    entity_type: str
    source_identity_sha256: str
    source_record_sha256: str
    source_artifact_sha256: str
    transformation_version: str
    company_id: UUID
    branch_id: UUID


@dataclass(frozen=True)
class OpenJobCandidate:
    evidence: SourceEvidence
    source_status: str
    customer_identity_sha256: str
    service_location_identity_sha256: str
    disposition: WorkDisposition | None
    disposition_evidence_sha256: str | None
    already_imported: bool = False


@dataclass(frozen=True)
class AppointmentCandidate:
    evidence: SourceEvidence
    job_identity_sha256: str
    source_status: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None


@dataclass(frozen=True)
class TechnicianIdentityBinding:
    company_id: UUID
    branch_id: UUID
    provider: str
    source_employee_identity_sha256: str
    enterprise_employee_id: UUID | None
    binding_evidence_sha256: str | None
    authoritative: bool


@dataclass(frozen=True)
class AssignmentCandidate:
    evidence: SourceEvidence
    parent_entity_type: str
    parent_identity_sha256: str
    technician_identity_sha256s: tuple[str, ...]


@dataclass(frozen=True)
class EstimateCandidate:
    evidence: SourceEvidence
    job_identity_sha256: str
    source_status: str
    accepted: bool
    required_to_perform_open_work: bool
    required_to_bill_open_work: bool


@dataclass(frozen=True)
class NoteCandidate:
    evidence: SourceEvidence
    parent_entity_type: str
    parent_identity_sha256: str
    inclusion_reasons: tuple[NoteReason, ...]
    occurred_at: datetime | None
    author_identity_sha256: str | None


@dataclass(frozen=True)
class AttachmentCandidate:
    evidence: SourceEvidence
    parent_entity_type: str
    parent_identity_sha256: str
    inclusion_reasons: tuple[ArtifactReason, ...]
    content_sha256: str | None
    availability_verified: bool


@dataclass(frozen=True)
class InvoiceCandidate:
    evidence: SourceEvidence
    job_identity_sha256: str
    source_status: str
    currency: str
    total_minor_units: int
    paid_minor_units: int
    balance_minor_units: int


@dataclass(frozen=True)
class PaymentApplicationCandidate:
    evidence: SourceEvidence
    invoice_identity_sha256: str
    currency: str
    payment_minor_units: int
    applied_minor_units: int
    unapplied_minor_units: int


@dataclass(frozen=True)
class SelectionResult:
    entity_type: str
    source_identity_sha256: str
    outcome: SelectionOutcome
    reason_code: str
    evidence_digest: str


@dataclass(frozen=True)
class ManifestEntityCount:
    entity_type: str
    source_count: int
    included_count: int
    excluded_count: int
    rejected_count: int
    owner_disposition_count: int
    duplicate_count: int


@dataclass(frozen=True)
class OpenWorkManifestDraft:
    company_id: UUID
    branch_id: UUID
    provider: str
    source_environment: str
    freeze_at: datetime
    cutover_date: str
    executing_code_sha: str
    source_artifact_sha256s: tuple[str, ...]
    transformation_versions: tuple[str, ...]
    ordered_results: tuple[SelectionResult, ...]
    entity_counts: tuple[ManifestEntityCount, ...]
    emergency_disposition_policy_sha256: str
    owner_policy_evidence_sha256: str


@dataclass(frozen=True)
class OpenWorkManifest:
    manifest_id: UUID
    manifest_digest: str
    replay_digest: str
    draft: OpenWorkManifestDraft


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _sha(value: str | None) -> bool:
    return (
        value is not None
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _validate_evidence(
    evidence: SourceEvidence, company_id: UUID, branch_id: UUID
) -> str | None:
    if evidence.company_id != company_id:
        return "company_mismatch"
    if evidence.branch_id != branch_id:
        return "branch_mismatch"
    if not evidence.provider or not evidence.transformation_version:
        return "unsupported_source_contract"
    if not all(
        _sha(value)
        for value in (
            evidence.source_identity_sha256,
            evidence.source_record_sha256,
            evidence.source_artifact_sha256,
        )
    ):
        return "evidence_mismatch"
    return None


def _result(
    evidence: SourceEvidence, outcome: SelectionOutcome, reason: str
) -> SelectionResult:
    digest = _digest((OPEN_WORK_CONTRACT_VERSION, evidence, outcome.value, reason))
    return SelectionResult(
        evidence.entity_type, evidence.source_identity_sha256, outcome, reason, digest
    )


class OpenWorkSelector:
    """Select hashed provider evidence only; it cannot import or mutate domains."""

    def __init__(
        self, *, company_id: UUID, branch_id: UUID, freeze_at: datetime
    ) -> None:
        if freeze_at.tzinfo is None:
            raise ValueError("freeze timestamp must be timezone-aware")
        self.company_id = company_id
        self.branch_id = branch_id
        self.freeze_at = freeze_at

    def job(self, item: OpenJobCandidate) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.source_status not in {
            "open",
            "in_progress",
            "needs_scheduling",
            "scheduled",
        }:
            return _result(
                item.evidence, SelectionOutcome.EXCLUDED, "not_open_at_freeze"
            )
        if not _sha(item.customer_identity_sha256) or not _sha(
            item.service_location_identity_sha256
        ):
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "missing_parent_identity"
            )
        if item.disposition is None or not _sha(item.disposition_evidence_sha256):
            return _result(
                item.evidence,
                SelectionOutcome.OWNER_DISPOSITION_REQUIRED,
                "in_flight_disposition_required",
            )
        if item.disposition is WorkDisposition.MIGRATE_TO_ENTERPRISE:
            if item.already_imported:
                return _result(
                    item.evidence,
                    SelectionOutcome.INCLUDED,
                    "existing_source_identity_idempotent",
                )
            return _result(
                item.evidence, SelectionOutcome.INCLUDED, "open_work_migration_approved"
            )
        if item.disposition is WorkDisposition.COMPLETE_IN_HCP:
            return _result(item.evidence, SelectionOutcome.EXCLUDED, "complete_in_hcp")
        return _result(item.evidence, SelectionOutcome.EXCLUDED, "explicitly_held")

    def appointment(
        self, item: AppointmentCandidate, *, selected_jobs: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.job_identity_sha256 not in selected_jobs:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_job_not_selected"
            )
        if item.source_status not in {"scheduled", "confirmed", "in_progress"}:
            return _result(
                item.evidence, SelectionOutcome.EXCLUDED, "not_future_or_in_flight"
            )
        if item.scheduled_start is None or item.scheduled_start.tzinfo is None:
            return _result(item.evidence, SelectionOutcome.REJECTED, "invalid_schedule")
        if (
            item.scheduled_end is not None
            and item.scheduled_end <= item.scheduled_start
        ):
            return _result(item.evidence, SelectionOutcome.REJECTED, "invalid_schedule")
        if (
            item.source_status != "in_progress"
            and (item.scheduled_end or item.scheduled_start) <= self.freeze_at
        ):
            return _result(
                item.evidence,
                SelectionOutcome.EXCLUDED,
                "appointment_ends_before_freeze",
            )
        return _result(
            item.evidence, SelectionOutcome.INCLUDED, "future_or_in_flight_appointment"
        )

    def estimate(
        self, item: EstimateCandidate, *, selected_jobs: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        required = item.required_to_perform_open_work or item.required_to_bill_open_work
        if item.job_identity_sha256 not in selected_jobs:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_job_not_selected"
            )
        if not item.accepted or item.source_status not in {"accepted", "approved"}:
            return _result(
                item.evidence, SelectionOutcome.EXCLUDED, "estimate_not_accepted"
            )
        if not required:
            return _result(
                item.evidence,
                SelectionOutcome.EXCLUDED,
                "nonessential_historical_estimate",
            )
        return _result(
            item.evidence,
            SelectionOutcome.INCLUDED,
            "accepted_estimate_required_for_open_work",
        )

    def note(
        self, item: NoteCandidate, *, selected_parents: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.parent_identity_sha256 not in selected_parents:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_not_selected"
            )
        if not item.inclusion_reasons:
            return _result(
                item.evidence, SelectionOutcome.EXCLUDED, "nonessential_historical_note"
            )
        if tuple(sorted(set(item.inclusion_reasons))) != item.inclusion_reasons:
            return _result(
                item.evidence,
                SelectionOutcome.REJECTED,
                "note_reasons_not_canonical",
            )
        if (
            item.occurred_at is None
            or item.occurred_at.tzinfo is None
            or not _sha(item.author_identity_sha256)
        ):
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "incomplete_note_provenance"
            )
        return _result(
            item.evidence, SelectionOutcome.INCLUDED, "operational_note_required"
        )

    def attachment(
        self, item: AttachmentCandidate, *, selected_parents: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.parent_identity_sha256 not in selected_parents:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_not_selected"
            )
        if not item.inclusion_reasons:
            return _result(
                item.evidence,
                SelectionOutcome.EXCLUDED,
                "nonessential_historical_artifact",
            )
        if tuple(sorted(set(item.inclusion_reasons))) != item.inclusion_reasons:
            return _result(
                item.evidence,
                SelectionOutcome.REJECTED,
                "artifact_reasons_not_canonical",
            )
        if not item.availability_verified or not _sha(item.content_sha256):
            return _result(
                item.evidence,
                SelectionOutcome.REJECTED,
                "artifact_unavailable_or_unverified",
            )
        return _result(
            item.evidence, SelectionOutcome.INCLUDED, "artifact_required_for_open_work"
        )

    def invoice(
        self, item: InvoiceCandidate, *, selected_jobs: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.job_identity_sha256 not in selected_jobs:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_job_not_selected"
            )
        if item.total_minor_units != item.paid_minor_units + item.balance_minor_units:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "monetary_mismatch"
            )
        if item.balance_minor_units <= 0 or item.source_status in {"paid", "void"}:
            return _result(
                item.evidence, SelectionOutcome.EXCLUDED, "invoice_not_open_unpaid"
            )
        return _result(
            item.evidence, SelectionOutcome.INCLUDED, "open_unpaid_invoice_continuity"
        )

    def payment(
        self, item: PaymentApplicationCandidate, *, selected_invoices: frozenset[str]
    ) -> SelectionResult:
        invalid = _validate_evidence(item.evidence, self.company_id, self.branch_id)
        if invalid:
            return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
        if item.invoice_identity_sha256 not in selected_invoices:
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "parent_invoice_not_selected"
            )
        if (
            item.payment_minor_units
            != item.applied_minor_units + item.unapplied_minor_units
        ):
            return _result(
                item.evidence, SelectionOutcome.REJECTED, "payment_application_mismatch"
            )
        return _result(
            item.evidence, SelectionOutcome.INCLUDED, "payment_application_continuity"
        )


def validate_technician_bindings(
    bindings: tuple[TechnicianIdentityBinding, ...],
    *,
    company_id: UUID,
    branch_id: UUID,
) -> tuple[str, ...]:
    blockers: set[str] = set()
    identities = [item.source_employee_identity_sha256 for item in bindings]
    if len(set(identities)) != len(identities):
        blockers.add("duplicate_technician_source_identity")
    targets = [
        item.enterprise_employee_id for item in bindings if item.enterprise_employee_id
    ]
    if len(set(targets)) != len(targets):
        blockers.add("employee_target_conflict")
    for item in bindings:
        if item.company_id != company_id:
            blockers.add("technician_company_mismatch")
        if item.branch_id != branch_id:
            blockers.add("technician_branch_mismatch")
        if not _sha(item.source_employee_identity_sha256):
            blockers.add("missing_technician_source_identity")
        if (
            not item.authoritative
            or item.enterprise_employee_id is None
            or not _sha(item.binding_evidence_sha256)
        ):
            blockers.add("unresolved_technician_identity")
    return tuple(sorted(blockers))


def validate_assignment(
    item: AssignmentCandidate,
    *,
    company_id: UUID,
    branch_id: UUID,
    selected_parents: frozenset[str],
    bindings: tuple[TechnicianIdentityBinding, ...],
) -> SelectionResult:
    invalid = _validate_evidence(item.evidence, company_id, branch_id)
    if invalid:
        return _result(item.evidence, SelectionOutcome.REJECTED, invalid)
    if item.parent_identity_sha256 not in selected_parents:
        return _result(
            item.evidence, SelectionOutcome.REJECTED, "assignment_parent_not_selected"
        )
    if len(set(item.technician_identity_sha256s)) != len(
        item.technician_identity_sha256s
    ):
        return _result(item.evidence, SelectionOutcome.REJECTED, "duplicate_assignment")
    if (
        tuple(sorted(item.technician_identity_sha256s))
        != item.technician_identity_sha256s
    ):
        return _result(
            item.evidence, SelectionOutcome.REJECTED, "assignment_not_canonical"
        )
    resolved = {
        binding.source_employee_identity_sha256
        for binding in bindings
        if binding.authoritative and binding.enterprise_employee_id is not None
    }
    if (
        not item.technician_identity_sha256s
        or not set(item.technician_identity_sha256s) <= resolved
    ):
        return _result(
            item.evidence,
            SelectionOutcome.OWNER_DISPOSITION_REQUIRED,
            "unresolved_technician_assignment",
        )
    return _result(
        item.evidence, SelectionOutcome.INCLUDED, "assignment_relationship_resolved"
    )


def seal_open_work_manifest(draft: OpenWorkManifestDraft) -> OpenWorkManifest:
    if (
        draft.freeze_at.tzinfo is None
        or draft.freeze_at.astimezone(OPERATIONAL_TIMEZONE).date()
        != TARGET_OPERATIONAL_FREEZE_DATE
        or draft.cutover_date != "2026-08-21"
    ):
        raise ValueError("August 21 freeze/cutover boundary is immutable")
    if len(draft.executing_code_sha) != 40 or any(
        c not in "0123456789abcdef" for c in draft.executing_code_sha
    ):
        raise ValueError("executing code SHA is invalid")
    digest_values = (
        *draft.source_artifact_sha256s,
        draft.emergency_disposition_policy_sha256,
        draft.owner_policy_evidence_sha256,
    )
    if any(not _sha(value) for value in digest_values):
        raise ValueError("manifest evidence digest is invalid")
    if (
        tuple(sorted(set(draft.source_artifact_sha256s)))
        != draft.source_artifact_sha256s
    ):
        raise ValueError("source artifacts must be unique and ordered")
    if (
        tuple(sorted(set(draft.transformation_versions)))
        != draft.transformation_versions
    ):
        raise ValueError("transformation versions must be unique and ordered")
    if not draft.transformation_versions:
        raise ValueError("at least one transformation version is required")
    expected_results = tuple(
        sorted(
            draft.ordered_results,
            key=lambda item: (item.entity_type, item.source_identity_sha256),
        )
    )
    if expected_results != draft.ordered_results:
        raise ValueError("manifest results must use deterministic ordering")
    if len(
        {
            (item.entity_type, item.source_identity_sha256)
            for item in draft.ordered_results
        }
    ) != len(draft.ordered_results):
        raise ValueError("duplicate source identity in manifest")
    counts_by_entity = {item.entity_type: item for item in draft.entity_counts}
    if len(counts_by_entity) != len(draft.entity_counts):
        raise ValueError("duplicate entity count")
    for entity, count in counts_by_entity.items():
        values = (
            count.source_count,
            count.included_count,
            count.excluded_count,
            count.rejected_count,
            count.owner_disposition_count,
            count.duplicate_count,
        )
        if any(value < 0 for value in values):
            raise ValueError(f"{entity} count cannot be negative")
        if count.source_count != sum(values[1:]):
            raise ValueError(f"{entity} counts do not reconcile")
        actual = [item for item in draft.ordered_results if item.entity_type == entity]
        if count.source_count != len(actual):
            raise ValueError(f"{entity} source count does not match manifest results")
        outcome_counts = {
            SelectionOutcome.INCLUDED: count.included_count,
            SelectionOutcome.EXCLUDED: count.excluded_count,
            SelectionOutcome.REJECTED: count.rejected_count,
            SelectionOutcome.OWNER_DISPOSITION_REQUIRED: count.owner_disposition_count,
        }
        if count.duplicate_count or any(
            expected != sum(item.outcome is outcome for item in actual)
            for outcome, expected in outcome_counts.items()
        ):
            raise ValueError(f"{entity} classified counts do not match results")
    digest = _digest((OPEN_WORK_CONTRACT_VERSION, draft))
    replay = _digest(
        (digest, tuple(item.evidence_digest for item in draft.ordered_results))
    )
    return OpenWorkManifest(uuid5(OPEN_WORK_NAMESPACE, digest), digest, replay, draft)
