"""Narrow compatibility adapter; paid time never becomes Job participation."""

from app.business_economics.evidence_acceptance import (
    TimeEntryProvenance as EconomicsTimeEntryProvenance,
)
from app.business_economics.evidence_acceptance import WorkdayTimeEvidence

from .contracts import ApprovedWorkdayTimeFact, TimeEntryProvenance


def to_economics_workday_time(
    fact: ApprovedWorkdayTimeFact,
) -> WorkdayTimeEvidence:
    fact.verify()
    provenance = (
        EconomicsTimeEntryProvenance.EMPLOYEE_PUNCH
        if fact.provenance is TimeEntryProvenance.EMPLOYEE_PUNCH
        else EconomicsTimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY
    )
    result = WorkdayTimeEvidence(
        workday_time_id=str(fact.entry_id),
        company_id=fact.company_id,
        employee_id=fact.employee_id,
        effective_date=fact.work_date,
        provenance=provenance,
        start_at=fact.start_at,
        end_at=fact.end_at,
        approved_duration_minutes=fact.approved_duration_minutes,
        approval_id=str(fact.approval_id),
        correction_revision_id=str(fact.revision_id),
        supersedes_revision_id=(
            str(fact.correction_lineage[-1]) if fact.correction_lineage else None
        ),
        entered_by_user_id=(
            fact.entered_by_user_id
            if fact.provenance is TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY
            else None
        ),
        punch_event_ids=tuple(str(value) for value in fact.punch_event_ids),
        evidence_digest=fact.evidence_digest,
    )
    result.validate()
    return result
