from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.operational_migration.open_work_cutover import (
    DAY_ONE_INCLUDED_ENTITIES,
    HISTORICAL_EXCLUSIONS_REMAIN,
    TARGET_OPERATIONAL_FREEZE_DATE,
    AppointmentCandidate,
    ArtifactReason,
    AssignmentCandidate,
    AttachmentCandidate,
    EstimateCandidate,
    InvoiceCandidate,
    ManifestEntityCount,
    NoteCandidate,
    NoteReason,
    OpenJobCandidate,
    OpenWorkManifestDraft,
    OpenWorkSelector,
    PaymentApplicationCandidate,
    SelectionOutcome,
    SourceEvidence,
    TechnicianIdentityBinding,
    WorkDisposition,
    seal_open_work_manifest,
    validate_assignment,
    validate_technician_bindings,
)

COMPANY = UUID(int=1)
BRANCH = UUID(int=2)
EMPLOYEE = UUID(int=3)
DIGEST = "a" * 64
CODE_SHA = "b" * 40
FREEZE_AT = datetime(2026, 8, 20, 22, 0, tzinfo=UTC)


def source(entity: str, identity: str = DIGEST) -> SourceEvidence:
    return SourceEvidence(
        "housecall_pro",
        entity,
        identity,
        "b" * 64,
        "c" * 64,
        "hcp-open-work/v1",
        COMPANY,
        BRANCH,
    )


SELECTOR = OpenWorkSelector(company_id=COMPANY, branch_id=BRANCH, freeze_at=FREEZE_AT)


def job(**changes: object) -> OpenJobCandidate:
    base = OpenJobCandidate(
        source("job"),
        "in_progress",
        "d" * 64,
        "e" * 64,
        WorkDisposition.MIGRATE_TO_ENTERPRISE,
        "f" * 64,
    )
    return replace(base, **changes)


def test_day_one_boundary_expands_only_operationally_required_history() -> None:
    assert DAY_ONE_INCLUDED_ENTITIES == (
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
    assert HISTORICAL_EXCLUSIONS_REMAIN == ("estimate", "note", "attachment")


@pytest.mark.parametrize(
    "status", ("open", "in_progress", "needs_scheduling", "scheduled")
)
def test_open_jobs_require_exactly_one_disposition(status: str) -> None:
    assert SELECTOR.job(job(source_status=status)).outcome is SelectionOutcome.INCLUDED
    blocked = SELECTOR.job(
        job(source_status=status, disposition=None, disposition_evidence_sha256=None)
    )
    assert blocked.outcome is SelectionOutcome.OWNER_DISPOSITION_REQUIRED
    assert blocked.reason_code == "in_flight_disposition_required"


@pytest.mark.parametrize(
    ("disposition", "reason"),
    (
        (WorkDisposition.COMPLETE_IN_HCP, "complete_in_hcp"),
        (WorkDisposition.EXPLICITLY_HELD, "explicitly_held"),
    ),
)
def test_in_flight_job_cannot_be_active_in_both_systems(
    disposition: WorkDisposition, reason: str
) -> None:
    result = SELECTOR.job(job(disposition=disposition))
    assert result.outcome is SelectionOutcome.EXCLUDED
    assert result.reason_code == reason


def test_existing_open_job_source_identity_is_recognized_idempotently() -> None:
    result = SELECTOR.job(job(already_imported=True))
    assert result.outcome is SelectionOutcome.INCLUDED
    assert result.reason_code == "existing_source_identity_idempotent"


def test_closed_job_and_missing_parent_are_not_selected() -> None:
    assert (
        SELECTOR.job(job(source_status="completed")).reason_code == "not_open_at_freeze"
    )
    assert (
        SELECTOR.job(job(customer_identity_sha256="bad")).reason_code
        == "missing_parent_identity"
    )


def test_future_and_in_flight_appointments_require_selected_job_and_valid_schedule() -> (
    None
):
    start = FREEZE_AT + timedelta(hours=8)
    item = AppointmentCandidate(
        source("appointment"), DIGEST, "scheduled", start, start + timedelta(hours=2)
    )
    assert (
        SELECTOR.appointment(item, selected_jobs=frozenset({DIGEST})).outcome
        is SelectionOutcome.INCLUDED
    )
    assert (
        SELECTOR.appointment(item, selected_jobs=frozenset()).reason_code
        == "parent_job_not_selected"
    )
    assert (
        SELECTOR.appointment(
            replace(item, scheduled_end=start), selected_jobs=frozenset({DIGEST})
        ).reason_code
        == "invalid_schedule"
    )
    historical = replace(
        item,
        scheduled_start=FREEZE_AT - timedelta(hours=2),
        scheduled_end=FREEZE_AT - timedelta(hours=1),
    )
    assert (
        SELECTOR.appointment(historical, selected_jobs=frozenset({DIGEST})).reason_code
        == "appointment_ends_before_freeze"
    )


def binding(**changes: object) -> TechnicianIdentityBinding:
    return replace(
        TechnicianIdentityBinding(
            COMPANY, BRANCH, "housecall_pro", DIGEST, EMPLOYEE, "b" * 64, True
        ),
        **changes,
    )


def test_technician_mapping_is_native_company_branch_scoped_and_fail_closed() -> None:
    assert (
        validate_technician_bindings((binding(),), company_id=COMPANY, branch_id=BRANCH)
        == ()
    )
    blockers = validate_technician_bindings(
        (binding(authoritative=False),), company_id=COMPANY, branch_id=BRANCH
    )
    assert blockers == ("unresolved_technician_identity",)
    blockers = validate_technician_bindings(
        (binding(branch_id=UUID(int=9)),), company_id=COMPANY, branch_id=BRANCH
    )
    assert blockers == ("technician_branch_mismatch",)


def test_assignments_require_selected_parent_unique_resolved_technicians() -> None:
    item = AssignmentCandidate(source("assignment"), "job", "c" * 64, (DIGEST,))
    result = validate_assignment(
        item,
        company_id=COMPANY,
        branch_id=BRANCH,
        selected_parents=frozenset({"c" * 64}),
        bindings=(binding(),),
    )
    assert result.outcome is SelectionOutcome.INCLUDED
    unresolved = validate_assignment(
        item,
        company_id=COMPANY,
        branch_id=BRANCH,
        selected_parents=frozenset({"c" * 64}),
        bindings=(),
    )
    assert unresolved.outcome is SelectionOutcome.OWNER_DISPOSITION_REQUIRED


def test_only_accepted_estimate_required_to_perform_or_bill_open_work_is_included() -> (
    None
):
    base = EstimateCandidate(source("estimate"), DIGEST, "accepted", True, True, False)
    assert (
        SELECTOR.estimate(base, selected_jobs=frozenset({DIGEST})).outcome
        is SelectionOutcome.INCLUDED
    )
    historical = replace(
        base, required_to_perform_open_work=False, required_to_bill_open_work=False
    )
    assert (
        SELECTOR.estimate(historical, selected_jobs=frozenset({DIGEST})).reason_code
        == "nonessential_historical_estimate"
    )
    assert (
        SELECTOR.estimate(
            replace(base, accepted=False), selected_jobs=frozenset({DIGEST})
        ).reason_code
        == "estimate_not_accepted"
    )


@pytest.mark.parametrize("reason", tuple(NoteReason))
def test_only_complete_provenanced_operational_notes_are_included(
    reason: NoteReason,
) -> None:
    item = NoteCandidate(
        source("note"),
        "job",
        DIGEST,
        (reason,),
        datetime(2026, 8, 1, tzinfo=UTC),
        "d" * 64,
    )
    assert (
        SELECTOR.note(item, selected_parents=frozenset({DIGEST})).outcome
        is SelectionOutcome.INCLUDED
    )
    assert (
        SELECTOR.note(
            replace(item, inclusion_reasons=()), selected_parents=frozenset({DIGEST})
        ).reason_code
        == "nonessential_historical_note"
    )
    assert (
        SELECTOR.note(
            replace(item, author_identity_sha256=None),
            selected_parents=frozenset({DIGEST}),
        ).reason_code
        == "incomplete_note_provenance"
    )


@pytest.mark.parametrize("reason", tuple(ArtifactReason))
def test_only_available_checksum_verified_required_artifacts_are_included(
    reason: ArtifactReason,
) -> None:
    item = AttachmentCandidate(
        source("attachment"), "job", DIGEST, (reason,), "d" * 64, True
    )
    assert (
        SELECTOR.attachment(item, selected_parents=frozenset({DIGEST})).outcome
        is SelectionOutcome.INCLUDED
    )
    assert (
        SELECTOR.attachment(
            replace(item, inclusion_reasons=()), selected_parents=frozenset({DIGEST})
        ).reason_code
        == "nonessential_historical_artifact"
    )
    assert (
        SELECTOR.attachment(
            replace(item, availability_verified=False),
            selected_parents=frozenset({DIGEST}),
        ).reason_code
        == "artifact_unavailable_or_unverified"
    )


def test_open_unpaid_invoice_and_payment_application_preserve_minor_units_exactly() -> (
    None
):
    invoice = InvoiceCandidate(
        source("invoice"), DIGEST, "issued", "USD", 10_001, 2_000, 8_001
    )
    result = SELECTOR.invoice(invoice, selected_jobs=frozenset({DIGEST}))
    assert result.outcome is SelectionOutcome.INCLUDED
    assert (
        SELECTOR.invoice(
            replace(invoice, balance_minor_units=8_000),
            selected_jobs=frozenset({DIGEST}),
        ).reason_code
        == "monetary_mismatch"
    )
    payment = PaymentApplicationCandidate(
        source("payment"),
        invoice.evidence.source_identity_sha256,
        "USD",
        2_000,
        1_500,
        500,
    )
    assert (
        SELECTOR.payment(payment, selected_invoices=frozenset({DIGEST})).outcome
        is SelectionOutcome.INCLUDED
    )
    assert (
        SELECTOR.payment(
            replace(payment, unapplied_minor_units=499),
            selected_invoices=frozenset({DIGEST}),
        ).reason_code
        == "payment_application_mismatch"
    )


def test_company_branch_and_source_evidence_fail_closed() -> None:
    result = SELECTOR.job(job(evidence=replace(source("job"), company_id=UUID(int=9))))
    assert result.reason_code == "company_mismatch"
    result = SELECTOR.job(
        job(evidence=replace(source("job"), source_record_sha256="bad"))
    )
    assert result.reason_code == "evidence_mismatch"


def test_manifest_is_deterministic_replayable_and_exactly_reconciled() -> None:
    result = SELECTOR.job(job())
    draft = OpenWorkManifestDraft(
        COMPANY,
        BRANCH,
        "housecall_pro",
        "owner_approved_export",
        FREEZE_AT,
        "2026-08-21",
        CODE_SHA,
        ("c" * 64,),
        ("hcp-open-work/v1",),
        (result,),
        (ManifestEntityCount("job", 1, 1, 0, 0, 0, 0),),
        "d" * 64,
        "e" * 64,
    )
    first = seal_open_work_manifest(draft)
    assert first == seal_open_work_manifest(draft)
    assert first.manifest_id.version == 5
    assert len(first.replay_digest) == 64
    with pytest.raises(ValueError, match="counts do not reconcile"):
        seal_open_work_manifest(
            replace(
                draft,
                entity_counts=(replace(draft.entity_counts[0], included_count=0),),
            )
        )
    with pytest.raises(ValueError, match="classified counts"):
        seal_open_work_manifest(
            replace(
                draft,
                entity_counts=(ManifestEntityCount("job", 1, 0, 1, 0, 0, 0),),
            )
        )


def test_manifest_rejects_duplicate_source_identity_and_changed_freeze() -> None:
    result = SELECTOR.job(job())
    draft = OpenWorkManifestDraft(
        COMPANY,
        BRANCH,
        "housecall_pro",
        "owner_approved_export",
        FREEZE_AT,
        "2026-08-21",
        CODE_SHA,
        ("c" * 64,),
        ("hcp-open-work/v1",),
        (result,),
        (ManifestEntityCount("job", 1, 1, 0, 0, 0, 0),),
        "d" * 64,
        "e" * 64,
    )
    with pytest.raises(ValueError, match="duplicate source identity"):
        seal_open_work_manifest(
            replace(
                draft,
                ordered_results=(result, result),
                entity_counts=(ManifestEntityCount("job", 2, 2, 0, 0, 0, 0),),
            )
        )
    with pytest.raises(ValueError, match="immutable"):
        seal_open_work_manifest(replace(draft, freeze_at=FREEZE_AT - timedelta(days=1)))


def test_freeze_contract_preserves_business_date_without_inventing_clock_time() -> None:
    assert TARGET_OPERATIONAL_FREEZE_DATE.isoformat() == "2026-08-20"
